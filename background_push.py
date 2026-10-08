"""Durable per-device push transitions. No broker/order actions."""
import copy
import json
import math
import re
import signal
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
        return f"≈ {price:.4f} EUR/Stück (geschätzt) · Gold {gold:.2f} USD/oz" + (' · FX-Aktualisierung verzögert' if model.get('fxDelayed') else '') if price else 'Eurokurs nicht berechenbar (KO/Modellgrenze)'
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
    if t is not None and not isinstance(t, dict):
        raise ValueError('Ungültige Trade-Einstellungen')
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
    started = time.monotonic()
    payload = json.dumps({**settings, 'bundle': bundle})
    # One fresh process after SIGABRT, within the original ten-second budget.
    # The evaluator rechecks source freshness; no previous result is reused.
    for attempt in range(2):
        remaining = 10 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError('Zeitlimit der Hintergrundanalyse erreicht')
        p = subprocess.run(['node', str(Path(__file__).with_name('background_analysis.js'))],
                           input=payload, text=True, capture_output=True, timeout=remaining)
        if p.returncode != -signal.SIGABRT or attempt:
            break
        print('BOB_ANALYSIS_RETRY signal=SIGABRT attempt=1', flush=True)
    if p.returncode:
        # The child reports only error metadata, never input/settings or quote payloads.
        try:
            error = json.loads(p.stderr)
            print('BOB_ANALYSIS_ERROR '+json.dumps(error, ensure_ascii=True), flush=True)
        except (ValueError, TypeError):
            print('BOB_ANALYSIS_ERROR exit='+str(p.returncode), flush=True)
        raise RuntimeError('Hintergrundanalyse fehlgeschlagen')
    result = json.loads(p.stdout)
    print('BOB_BACKGROUND_ANALYSIS ready='+str(result.get('ready'))+' priceFresh='+str(result.get('priceFresh'))+' duration_ms='+str(round((time.monotonic()-started)*1000)), flush=True)
    return result


def failed_analysis_market(bundle):
    """Preserve a genuine source clock when computation fails, without approving it."""
    from datetime import datetime
    at = None
    try:
        stamp = datetime.fromisoformat(bundle['spots']['spot_price_as_of'].replace('Z', '+00:00'))
        candidate = stamp.timestamp()*1000
        if stamp.tzinfo is not None and 0 < candidate <= time.time()*1000:
            at = candidate
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        pass
    return {'ready': False, 'priceFresh': False, 'analysisError': True, 'dataAt': at}


def advance(previous, settings, market, general, trade_enabled, now=None, log=True):
    settings = copy.deepcopy(settings)
    fx = market.get('fx') or {}
    model = (settings.get('trade') or {}).get('product')
    if model and positive(fx.get('rate')):
        from datetime import datetime
        try:
            stamp = datetime.fromisoformat(fx.get('fetchedAt','').replace('Z','+00:00')).timestamp()*1000
            clock = time.time()*1000 if now is None else now
            if 0 <= clock-stamp:
                model['fxScenario'] = fx['rate']
                model['fxDelayed'] = bool(fx.get('error')) or clock-stamp>90000
        except (ValueError, TypeError):
            pass
    now = int(time.time()*1000) if now is None else now
    state = copy.deepcopy(previous or {})
    if not general and not trade_enabled:
        state.pop('trade', None)
        return state, []
    events = []
    def audit(kind, outcome, reason):
        history = state.setdefault('pushHistory', [])
        # Keep a bounded durable history without adding an entry every tick.
        if history and history[-1]['kind'] == kind and history[-1]['outcome'] == outcome and now-history[-1]['at'] < 300000:
            return
        history.append({'at': now, 'kind': kind, 'outcome': outcome, 'reason': reason})
        del history[:-50]
        if log:print('BOB_PUSH_DECISION '+json.dumps({'kind': kind, 'outcome': outcome, 'reason': reason[:160]}, ensure_ascii=True), flush=True)
    def add(kind, title, reason, channel='trade'):
        audit(kind, 'planned', reason[:160])
        product=(settings.get('trade') or {}).get('product') if channel=='trade' else None
        if product:
            reason=reason+' · '+product['isin']+' · Modellreferenz '+product['referenceAt']+'; verfügbarer Wechselkurs und gespeicherte Produktbedingungen. Kein bestätigter DEGIRO-Kurs.'
        events.append({'title': title, 'body': reason, 'tag': 'bob-background-'+channel,
                       'data': {'kind': channel, 'eventKind': kind, 'url': '/', 'dataAt': market.get('dataAt'),
                                'expiresAt': now+180000, 'tradeId': (settings.get('trade') or {}).get('tradeId')}})
    healthy = market.get('ready') is True and market.get('priceFresh') is True
    channel = 'trade' if trade_enabled and settings.get('trade') else 'general'
    # Notification debounce never makes unhealthy data eligible for analysis.
    announced = state.setdefault('announcedHealthy', state.get('healthy', True))
    pending = state.get('healthPending')
    if healthy == announced:
        state.pop('healthPending', None)
    elif not pending or pending['value'] != healthy:
        state['healthPending'] = {'value': healthy, 'since': now, 'count': 1, 'checkedAt': now}
    elif now-pending['checkedAt'] >= 25000:
        pending.update(count=pending['count']+1, checkedAt=now)
    pending = state.get('healthPending')
    confirmed = pending and pending['count'] >= (2 if healthy else 3) and now-pending['since'] >= (30000 if healthy else 60000)
    if healthy != announced and not confirmed:
        audit('data-status', 'suppressed', 'Statuswechsel noch nicht mehrfach bestätigt')
    if confirmed:
        if not healthy:
            reason = ('Die Hintergrundanalyse ist fehlgeschlagen. Eine aktuelle Bewertung und Trade-Überwachung sind nicht bestätigt.'
                      if market.get('analysisError') else 'Aktualität oder zeitliche Abstimmung der vorhandenen Markt-/Analysedaten nicht bestätigt. Berechnung mit vorhandenen Werten läuft weiter; Überwachung eingeschränkt.')
            add('data-unavailable', 'DATENSTATUS · Überwachung eingeschränkt', reason, channel)
        else:
            add('data-recovered', 'DATENSTATUS · Überwachung fortgesetzt', 'Aktuelle Daten wieder vorhanden. Keine Entwarnung für einen Trade.', channel)
        state['announcedHealthy'] = healthy
        state.pop('healthPending', None)
    state['healthy'] = healthy
    direction = market.get('direction', 'NEUTRAL') if healthy else 'NEUTRAL'
    mtf = market.get('mtf', 'NEUTRAL') if healthy else 'NEUTRAL'
    if general and healthy:
        notified = state.setdefault('notifiedDirection', state.get('direction'))
        pending = state.get('signalPending')
        if direction not in ('LONG', 'SHORT') or direction == notified:
            state.pop('signalPending', None)
        elif not pending or pending['direction'] != direction:
            state['signalPending'] = {'direction': direction, 'since': now, 'dataAt': market.get('dataAt')}
            audit('signal-change', 'suppressed', 'Richtung wartet auf erneute aktuelle Bestätigung')
        elif now-pending['since'] >= 30000 and positive(market.get('dataAt')) and market['dataAt'] != pending['dataAt']:
            add('signal-change', 'EINSTIEG · '+direction, 'Neuer Einstieg: '+direction+' bestätigt · MTF '+mtf+'. Keine Produktfreigabe.', 'general')
            state['notifiedDirection'] = direction
            state.pop('signalPending', None)
        # MTF confirmation is included in the direction message, never a second alert.
    else:
        state.pop('signalPending', None)
    if healthy:
        state.update(direction=direction, mtf=mtf)
    t = settings.get('trade') if trade_enabled else None
    if not t:
        state.pop('trade', None)
        return state, present_events(events, settings, market)
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
        return state, present_events(events, settings, market)
    p, stop, entry, risk = market['price'], old['stop'], t['entry'], t['initialRisk']
    personal, model = t.get('personalRisk'), t.get('product')
    if model and (p <= model['ko'] if t['dir']=='LONG' else p >= model['ko']) and not old.get('koSent'):
        add('ko-hit', 'TRADE-WARNUNG · KO-Barriere erreicht', 'Goldreferenz erreicht die gespeicherte KO-Barriere. Produktstatus bei DEGIRO prüfen; kein bestätigter Emittentenstatus.')
        old['koSent'] = True
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

    main_trend = market.get('trendContext') or {}
    trend_intact = healthy and main_trend.get('available') is True and main_trend.get('intact') is True and main_trend.get('direction') == t['dir']
    long = t['dir']=='LONG'
    reached = p<=stop if long else p>=stop
    near = max((market.get('atr') or 0)*.25, 1)
    phase = 'hit' if reached else 'near' if abs(p-stop)<=near else 'clear'
    send_hit = reached and not old.get('stopHitSent')
    send_near = phase == 'near' and phase != old.get('stopPhase') and now-old.get('stopNearAt', -300000) >= 300000 and not old.get('stopHitSent')
    if send_hit or send_near:
        add('stop-'+phase, 'TRADE-WARNUNG · '+('Stop erreicht' if reached else 'Stop wird knapp'), f"{t['dir']} · Modell-Stop {level_text(t,stop)}. Position prüfen.")
        if reached:
            old['stopHitSent'] = True
        else:
            old['stopNearAt'] = now
    old['stopPhase'] = phase
    target = old.get('target')
    target_hit = positive(target) and (p>=target if long else p<=target)
    if target_hit and not old.get('targetSent'):
        add('target', 'TRADE-WARNUNG · Ziel erreicht', f"{t['dir']} · Ziel {level_text(t,target)} anhand Goldreferenz erreicht. {('Haupttrend intakt: Fortsetzung mit geschütztem Stop prüfen.' if trend_intact else 'Fortsetzung nicht bestätigt: Gewinnschutz und Stop prüfen; kein automatischer Ausstieg.')}")
        old['targetSent'] = True
    if healthy and not trend_intact and direction in ('LONG','SHORT') and direction != t['dir'] and direction != old.get('opposite'):
        add('reversal', 'TRADE-WARNUNG · Richtungswechsel', f"Bestätigtes {direction}-Signal gegen deinen {t['dir']}-Trade. Schließen prüfen.")
        old['opposite'] = direction
    elif healthy and direction == t['dir']:
        old['opposite'] = None
    if reached or not healthy:
        return state, present_events(events, settings, market)
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
    notified_stop = old.get('notifiedStop', stop)
    change = abs(desired-notified_stop)
    minimum = max((market.get('atr') or 0)*.25, risk*.1, .01)
    if change >= minimum and now-old.get('stopUpdateAt', -300000) >= 300000:
        add('profit-protection' if stage else 'trailing-stop', 'TRADE-WARNUNG · Stop nachziehen', f"{t['dir']} · Neuer Modell-Stop {level_text(t,desired)} (zuletzt gemeldet {level_text(t,notified_stop)}); {r:.1f}R (Goldplan). Bei DEGIRO selbst anpassen.")
        old.update(notifiedStop=desired, stopUpdateAt=now)
    elif change > .0001:
        audit('trailing-stop', 'suppressed', 'Änderung zu klein oder letzte Meldung weniger als fünf Minuten her')
    old.setdefault('notifiedStop', stop)
    if abs(desired-stop)>.0001:
        old['stop'] = desired
    # Extend only after the old objective is reached and a new closed bar confirms continuation.
    candidate = market.get('suggestedTarget')
    bar = market.get('analysisBarAt')
    macd, signal = market.get('macd'), market.get('signal')
    strong = (direction==t['dir'] and mtf==t['dir'] and
              isinstance(macd,(int,float)) and isinstance(signal,(int,float)) and
              (macd>=signal and market.get('score',0)>=70 if long else macd<=signal and market.get('score',100)<=30))
    strong = (main_trend.get('phase') == 'CONTINUATION') if trend_intact else strong
    target_plan = market.get('suggestedTargetPlan') or {}
    if target_hit and strong and target_plan.get('entrySuitable') is not False and positive(candidate) and positive(bar) and bar>old.get('targetBarAt',0):
        step=max(risk*.5, (market.get('atr') or 0)*.5)
        beyond = candidate>=max(p,target)+step if long else candidate<=min(p,target)-step
        if beyond:
            old.update(target=candidate,targetSent=False,targetBarAt=bar)
            add('target-extension','TRADE-PLAN · Ziel erreicht – neues Ziel',
                f"{t['dir']} · Bisheriges Ziel erreicht. Neues Ziel {level_text(t,candidate)}; Stop {level_text(t,old['stop'])}. {('Haupttrend-Fortsetzung durch geschlossene Kerze bestätigt' if trend_intact else 'Richtung, MTF und Momentum weiter bestätigt')}. Vorschlag bei DEGIRO selbst übernehmen. {target_plan.get('warning','')}")
    estimated_now=product_price(t.get('product'),p)
    product_in_profit=not t.get('product') or (estimated_now is not None and estimated_now>t['product']['entry'])
    weak = not trend_intact and (main_trend.get('phase') == 'WEAKENING' or mtf != t['dir'] or (market.get('score',50)<65 if long else market.get('score',50)>35))
    if weak and r>=1 and product_in_profit and not old.get('weak'):
        add('profit-weak', 'TRADE-WARNUNG · Gewinn schützen', f"{t['dir']} · Momentum schwächer bei {r:.1f}R (Goldplan). Stop/Position prüfen.")
    old['weak'] = weak and r>=1 and product_in_profit
    return state, present_events(events, settings, market)




def present_events(events, settings, market):
    """Presentation only: retain triggers/checkpoints, combine compatible messages."""
    events = copy.deepcopy(events)
    kinds = {e['data']['eventKind'] for e in events}
    if 'target-extension' in kinds:
        events = [e for e in events if e['data']['eventKind'] != 'target']
    trade = settings.get('trade')
    trend = market.get('trendContext') or {}
    for event in events:
        if event['data']['eventKind'] == 'signal-change' and trade:
            intact = trend.get('available') and trend.get('intact') and trend.get('direction') == trade['dir']
            event['body'] += ' Dein '+trade['dir']+'-Trade: '+('Haupttrend intakt.' if intact else 'Bestand separat prüfen; Einstiegssignal ist kein automatischer Ausstieg.')
    return events


def compose_events(events):
    """Urgent action first; advisory plans never compete with an exit warning."""
    priority = {'ko-hit': 0, 'stop-hit': 1, 'personal-risk': 2, 'reversal': 3,
                'data-unavailable': 4, 'stop-near': 5, 'target-extension': 6, 'target': 7}
    ordered = sorted(events, key=lambda e: priority.get(e['data']['eventKind'], 8))
    message = copy.deepcopy(ordered[0])
    urgent = ordered[0]['data']['eventKind'] in ('ko-hit', 'stop-hit', 'reversal')
    advisory = {'target', 'target-extension', 'trailing-stop', 'profit-protection', 'profit-weak', 'signal-change'}
    visible = [e for e in ordered if not urgent or e['data']['eventKind'] not in advisory]
    message['body'] = ' | '.join(e['body'] for e in visible)
    message['data']['events'] = [e['data']['eventKind'] for e in ordered]
    if any(e['data']['kind'] == 'trade' for e in ordered):
        message['data']['kind'] = 'trade'
    return message

