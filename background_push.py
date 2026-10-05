"""Durable per-device push transitions. No broker/order actions."""
import copy
import json
import math
import re
import subprocess
import time
from pathlib import Path


def positive(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def product_model(value, direction):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('simpleSpotTurbo') is not True or value.get('referenceConfirmed') is not True or value.get('currency') != 'EUR':
        raise ValueError('Bestätigtes Gold-Spot-Turbo-Modell in EUR fehlt')
    if value.get('direction') != direction or not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]', str(value.get('isin', ''))):
        raise ValueError('Produktidentität oder Trade-Richtung widersprüchlich')
    keys = ('bid','goldReference','fxReference','fxScenario','ratio','strike','ko','entry','quantity')
    if not all(positive(value.get(k)) for k in keys) or value['quantity'] % 1:
        raise ValueError('Produktreferenz unvollständig')
    if not all(isinstance(value.get(k),str) and 0<len(value[k])<=2000 for k in ('source','referenceAt')):
        raise ValueError('Produktquelle oder Referenzzeit fehlt')
    d = 1 if direction == 'LONG' else -1
    if d*(value['goldReference']-value['ko'])<=0:
        raise ValueError('Produktreferenz jenseits der KO-Barriere')
    return {k:value[k] for k in (*keys,'isin','direction','currency','source','referenceAt','simpleSpotTurbo','referenceConfirmed')}


def product_price(model, gold):
    if not model or not positive(gold):
        return None
    d = 1 if model['direction']=='LONG' else -1
    if d*(gold-model['ko'])<=0:
        return None
    price=model['bid']+d*model['ratio']*((gold-model['strike'])*model['fxScenario']-(model['goldReference']-model['strike'])*model['fxReference'])
    return price if positive(price) else None


def level_text(trade, gold):
    model=trade.get('product')
    price=product_price(model,gold)
    if model:
        return f"≈ {price:.4f} EUR/Stück (berechnet)" if price else 'Eurokurs nicht berechenbar (KO/Modellgrenze)'
    return f"{gold:.2f} USD/oz (Goldreferenz; Produktdaten fehlen)"


def config(value):
    value = value if isinstance(value, dict) else {}
    tf = value.get('timeframe', '15m')
    if tf not in ('5m', '15m', '1h'):
        raise ValueError('Ungültige Push-Zeitebene')
    result = {'timeframe': tf, 'trailAtr': 1.5, 'trade': None}
    mult = value.get('trailAtr', 1.5)
    if not positive(mult) or mult > 10:
        raise ValueError('Ungültiger ATR-Faktor')
    result['trailAtr'] = mult
    t = value.get('trade')
    if t and t.get('active') and not t.get('test'):
        if t.get('dir') not in ('LONG', 'SHORT') or not all(positive(t.get(k)) for k in ('entry', 'stop', 'initialRisk')):
            raise ValueError('Einstieg, Stop und Anfangsrisiko fehlen für Hintergrund-Push')
        if t.get('instrument') != 'XAU/USD':
            raise ValueError('Trade-Basiswert für Hintergrund-Push muss XAU/USD sein')
        if not isinstance(t.get('tradeId'), str) or not 1 <= len(t['tradeId']) <= 100:
            raise ValueError('Trade-ID fehlt für Hintergrund-Push')
        result['trade'] = {k: t.get(k) for k in ('tradeId', 'dir', 'entry', 'stop', 'initialRisk', 'target', 'instrument')}
        result['trade']['active'] = True
        personal = t.get('personalRisk')
        result['trade']['personalRisk'] = None
        if personal is not None:
            if not isinstance(personal, dict) or not positive(personal.get('account')) or not positive(personal.get('percent')) or personal['percent'] > 100:
                raise ValueError('Persönliche Risikoeinstellung ungültig')
            result['trade']['personalRisk'] = {'account': personal['account'], 'percent': personal['percent']}

        result['trade']['product'] = product_model(t.get('product'), t['dir'])
        if t.get('target') is not None and not positive(t['target']):
            raise ValueError('Ungültiges Kursziel')
    return result


def analyze(bundle, settings):
    p = subprocess.run(['node', str(Path(__file__).with_name('background_analysis.js'))],
                       input=json.dumps({**settings, 'bundle': bundle}), text=True, capture_output=True, timeout=10, check=True)
    return json.loads(p.stdout)


def advance(previous, settings, market, general, trade_enabled, now=None):
    now = int(time.time()*1000) if now is None else now
    state = copy.deepcopy(previous or {})
    if not general and not trade_enabled:
        state.pop('trade', None)
        return state, []
    events = []
    def add(kind, title, reason, channel='trade'):
        product=(settings.get('trade') or {}).get('product') if channel=='trade' else None
        if product:
            reason=product['isin']+' · '+reason+' · Modellreferenz '+product['referenceAt']+'; konstante FX-/Produktbedingungen. Kein bestätigter DEGIRO-Kurs.'
        events.append({'title': title, 'body': reason, 'tag': 'bob-background-'+channel,
                       'data': {'kind': channel, 'eventKind': kind, 'url': '/', 'dataAt': market.get('dataAt'),
                                'expiresAt': now+180000, 'tradeId': (settings.get('trade') or {}).get('tradeId')}})
    healthy = market.get('ready') is True and market.get('priceFresh') is True
    channel = 'trade' if trade_enabled and settings.get('trade') else 'general'
    if state.get('healthy') != healthy:
        if not healthy:
            add('data-unavailable', 'DATENSTATUS · Überwachung eingeschränkt', 'Aktuelle Markt-/Analysedaten fehlen. Berechnung mit vorhandenen Werten läuft weiter; keine aktuelle Bestätigung.', channel)
        elif state.get('healthy') is False:
            add('data-recovered', 'DATENSTATUS · Überwachung fortgesetzt', 'Aktuelle Daten wieder vorhanden. Keine Entwarnung für einen Trade.', channel)
    state['healthy'] = healthy
    direction = market.get('direction', 'NEUTRAL') if healthy else 'NEUTRAL'
    mtf = market.get('mtf', 'NEUTRAL') if healthy else 'NEUTRAL'
    if general and healthy:
        if direction in ('LONG','SHORT') and direction != state.get('direction'):
            add('signal-change', 'MARKTSIGNAL · '+direction, 'Bestätigtes Bob-Signal '+direction+' · MTF '+mtf+'. Keine Produktfreigabe.', 'general')
        elif mtf in ('LONG','SHORT') and mtf == direction and mtf != state.get('mtf'):
            add('mtf-change', 'MARKTSIGNAL · MTF '+mtf, 'Multi-Timeframe-Ausrichtung geändert. Keine Produktfreigabe.', 'general')
    if healthy:
        state.update(direction=direction, mtf=mtf)
    t = settings.get('trade') if trade_enabled else None
    if not t:
        state.pop('trade', None)
        return state, events
    old = state.get('trade', {})
    if old.get('tradeId') != t['tradeId']:
        old = {**t, 'stage': 0}
    # Never loosen a previously suggested model stop on a stale browser sync.
    old['stop'] = max(old['stop'], t['stop']) if t['dir']=='LONG' else min(old['stop'], t['stop'])
    old['product'] = t.get('product')
    if positive(t.get('target')):
        old['target'] = (max if t['dir']=='LONG' else min)(old.get('target') or t['target'], t['target'])
    state['trade'] = old
    session = market.get('session') or {}
    if session.get('closeReminder') and session.get('date') and old.get('intradayEndDate') != session['date']:
        add('intraday-end', 'INTRADAY · Tagesende', 'Bobs Tagesende-Zeit 21:45 (Zürich) ist erreicht. Offene Position und Schließung bei DEGIRO prüfen. Produkthandelszeiten können abweichen. Keine automatische Order.')
        old['intradayEndDate'] = session['date']
        events[-1]['tag'] = 'bob-intraday-end-' + t['tradeId']
    if not market.get('priceFresh') or not positive(market.get('price')):
        return state, events
    p, stop, entry, risk = market['price'], old['stop'], t['entry'], t['initialRisk']
    personal, model = t.get('personalRisk'), t.get('product')
    if personal and model:
        budget = personal['account'] * personal['percent'] / 100
        estimated = product_price(model, p)
        marker = [personal['account'], personal['percent'], model['entry'], model['quantity']]
        if estimated is not None and (model['entry'] - estimated) * model['quantity'] >= budget and old.get('personalRiskSent') != marker:
            loss = (model['entry'] - estimated) * model['quantity']
            add('personal-risk', 'Deine persönliche Risikogrenze wurde erreicht',
                f"Berechneter Verlust ≈ {loss:.2f} EUR; Risikobudget {budget:.2f} EUR ({personal['percent']:g}% von {personal['account']:g} EUR). Ohne Gebühren. Position prüfen; kein automatischer Verkauf.")
            events[-1]['tag'] = 'bob-personal-risk-' + t['tradeId']
            old['personalRiskSent'] = marker

    long = t['dir']=='LONG'
    reached = p<=stop if long else p>=stop
    near = max((market.get('atr') or 0)*.25, 1)
    phase = 'hit' if reached else 'near' if abs(p-stop)<=near else 'clear'
    if phase != old.get('stopPhase') and phase != 'clear':
        add('stop-'+phase, 'TRADE-WARNUNG · '+('Stop erreicht' if reached else 'Stop wird knapp'), f"{t['dir']} · Modell-Stop {level_text(t,stop)}. Position prüfen.")
    old['stopPhase'] = phase
    target = old.get('target')
    target_hit = positive(target) and (p>=target if long else p<=target)
    if target_hit and not old.get('targetSent'):
        add('target', 'TRADE-WARNUNG · Ziel erreicht', f"{t['dir']} · Ziel {level_text(t,target)} anhand Goldreferenz erreicht. Ausstieg/Stop prüfen.")
        old['targetSent'] = True
    if healthy and direction in ('LONG','SHORT') and direction != t['dir'] and direction != old.get('opposite'):
        add('reversal', 'TRADE-WARNUNG · Richtungswechsel', f"Bestätigtes {direction}-Signal gegen deinen {t['dir']}-Trade. Schließen prüfen.")
        old['opposite'] = direction
    elif healthy and direction == t['dir']:
        old['opposite'] = None
    if reached or not healthy:
        return state, events
    r = (p-entry if long else entry-p)/risk
    stage = 2 if r>=2 else 1.5 if r>=1.5 else 1 if r>=1 else 0
    desired = stop
    if stage > old.get('stage',0):
        lock = 1 if stage>=2 else .5 if stage>=1.5 else 0
        level = entry+risk*lock if long else entry-risk*lock
        desired = max(stop,level) if long else min(stop,level)
        old['stage'] = stage
    candidate = market.get('suggestedStop')
    if positive(candidate) and (candidate<p if long else candidate>p):
        desired = max(desired,candidate) if long else min(desired,candidate)
    if abs(desired-stop)>.0001:
        add('profit-protection' if stage else 'trailing-stop', 'TRADE-WARNUNG · Stop nachziehen', f"{t['dir']} · Neuer Modell-Stop {level_text(t,desired)} (vorher {level_text(t,stop)}); {r:.1f}R (Goldplan). Bei DEGIRO selbst anpassen.")
        old['stop'] = desired
    # Extend only after the old objective is reached and a new closed bar confirms continuation.
    candidate = market.get('suggestedTarget')
    bar = market.get('analysisBarAt')
    macd, signal = market.get('macd'), market.get('signal')
    strong = (direction==t['dir'] and mtf==t['dir'] and
              isinstance(macd,(int,float)) and isinstance(signal,(int,float)) and
              (macd>=signal and market.get('score',0)>=70 if long else macd<=signal and market.get('score',100)<=30))
    if target_hit and strong and positive(candidate) and positive(bar) and bar>old.get('targetBarAt',0):
        step=max(risk*.5, (market.get('atr') or 0)*.5)
        beyond = candidate>=max(p,target)+step if long else candidate<=min(p,target)-step
        if beyond:
            old.update(target=candidate,targetSent=False,targetBarAt=bar)
            add('target-extension','TRADE-PLAN · Neues Ziel vorgeschlagen',
                f"{t['dir']} · Bisheriges Ziel erreicht. Neues Ziel {level_text(t,candidate)}; Stop {level_text(t,old['stop'])}. Richtung, MTF und Momentum weiter bestätigt. Vorschlag bei DEGIRO selbst übernehmen.")
    estimated_now=product_price(t.get('product'),p)
    product_in_profit=not t.get('product') or (estimated_now is not None and estimated_now>t['product']['entry'])
    weak = mtf != t['dir'] or (market.get('score',50)<65 if long else market.get('score',50)>35)
    if weak and r>=1 and product_in_profit and not old.get('weak'):
        add('profit-weak', 'TRADE-WARNUNG · Gewinn schützen', f"{t['dir']} · Momentum schwächer bei {r:.1f}R (Goldplan). Stop/Position prüfen.")
    old['weak'] = weak and r>=1 and product_in_profit
    return state, events
