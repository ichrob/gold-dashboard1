"""Durable per-device push transitions. No broker/order actions."""
import copy
import json
import math
import subprocess
import time
from pathlib import Path


def positive(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


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
        elif mtf in ('LONG','SHORT') and mtf != state.get('mtf'):
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
    state['trade'] = old
    if not market.get('priceFresh') or not positive(market.get('price')):
        return state, events
    p, stop, entry, risk = market['price'], old['stop'], t['entry'], t['initialRisk']
    long = t['dir']=='LONG'
    reached = p<=stop if long else p>=stop
    near = max((market.get('atr') or 0)*.25, 1)
    phase = 'hit' if reached else 'near' if abs(p-stop)<=near else 'clear'
    if phase != old.get('stopPhase') and phase != 'clear':
        add('stop-'+phase, 'TRADE-WARNUNG · '+('Stop erreicht' if reached else 'Stop wird knapp'), f"{t['dir']} · XAU/USD {p:.2f} · Modell-Stop {stop:.2f}. Position prüfen.")
    old['stopPhase'] = phase
    target = t.get('target')
    target_hit = positive(target) and (p>=target if long else p<=target)
    if target_hit and not old.get('targetSent'):
        add('target', 'TRADE-WARNUNG · Ziel erreicht', f"{t['dir']} · Ziel {target:.2f} USD erreicht. Gewinn sichern prüfen.")
        old['targetSent'] = True
    if healthy and direction in ('LONG','SHORT') and direction != t['dir'] and direction != old.get('opposite'):
        add('reversal', 'TRADE-WARNUNG · Richtungswechsel', f"Bestätigtes {direction}-Signal gegen deinen {t['dir']}-Trade. Schließen prüfen.")
        old['opposite'] = direction
    elif healthy and direction == t['dir']:
        old['opposite'] = None
    if reached or target_hit or not healthy:
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
        add('profit-protection' if stage else 'trailing-stop', 'TRADE-WARNUNG · Stop nachziehen', f"{t['dir']} · Neuer Modell-Stop {desired:.2f} USD (vorher {stop:.2f}); {r:.1f}R. Bei DEGIRO selbst anpassen.")
        old['stop'] = desired
    weak = mtf != t['dir'] or (market.get('score',50)<65 if long else market.get('score',50)>35)
    if weak and r>=1 and not old.get('weak'):
        add('profit-weak', 'TRADE-WARNUNG · Gewinn schützen', f"{t['dir']} · Momentum schwächer bei {r:.1f}R. Stop/Position prüfen.")
    old['weak'] = weak and r>=1
    return state, events
