"""Trade-specific, closed-candle Fibonacci monitoring. No order execution."""
import math
import time

STEPS = {'5m': 300000, '15m': 900000, '1h': 3600000}
LEVELS = {'r382': '38,2 %', 'r500': '50 %', 'r618': '61,8 %', 'r786': '78,6 %', 'e1272': '127,2 %', 'e1618': '161,8 %'}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Ungültiger Monitorwert')
    return float(value)


def validate_monitor(value, now_ms=None):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('direction') not in ('LONG', 'SHORT') or value.get('timeframe') not in STEPS:
        raise ValueError('Ungültige Fibonacci-Überwachung')
    trade_id = value.get('tradeId')
    if not isinstance(trade_id, str) or not 1 <= len(trade_id) <= 100:
        raise ValueError('Trade-ID fehlt')
    instrument = value.get('instrument')
    if instrument not in ('XAU/USD', 'GC=F'):
        raise ValueError('Historischer Basiswert nicht bestätigt')
    levels = value.get('levels')
    if not isinstance(levels, dict) or set(levels) != set(LEVELS):
        raise ValueError('Fibonacci-Level unvollständig')
    levels = {k: number(levels[k]) for k in LEVELS}
    started = number(value.get('startedAt'))
    now_ms = now_ms or time.time()*1000
    if started > now_ms+5000 or started < 1000000000000:
        raise ValueError('Trade-Start außerhalb des Überwachungsfensters')
    return dict(tradeId=trade_id, direction=value['direction'], timeframe=value['timeframe'], instrument=instrument,
                levels=levels, startedAt=started, processedAt=started, previousClose=number(value.get('previousClose')))


def advance_monitor(monitor, bars, now_ms=None):
    """Return a new checkpoint and alerts; caller persists only after delivery."""
    state = dict(monitor)
    now_ms = now_ms or time.time()*1000
    step = STEPS[state['timeframe']]
    usable = []
    for b in bars or []:
        try:
            opened, close = number(b.get('openTime')), number(b.get('close'))
            if b.get('isOpen') or opened+step > now_ms or b.get('instrument') != state['instrument']:
                continue
            usable.append((opened+step, close))
        except (ValueError, AttributeError):
            continue
    usable = sorted(set(usable))
    if not usable or now_ms-usable[-1][0] > step*2:
        return state, [], 'unavailable'
    alerts = []
    for closed_at, close in usable:
        if closed_at <= state['processedAt']:
            continue
        # Do not retrospectively claim a crossing across a data outage.
        if closed_at-state['processedAt'] > step*2 or now_ms-closed_at > step*2:
            state.update(processedAt=closed_at, previousClose=close)
            continue
        prev = state['previousClose']
        for key, level in state['levels'].items():
            up = prev <= level < close
            down = close < level <= prev
            if not (up or down):
                continue
            favorable = up == (state['direction'] == 'LONG')
            alerts.append(dict(signalId=f"fib:{state['tradeId']}:{int(closed_at)}:{key}:{'up' if up else 'down'}",
                               kind='fibonacci-break', level=key, levelLabel=LEVELS[key], levelPrice=level,
                               price=close, crossed='up' if up else 'down', favorable=favorable,
                               direction=state['direction'], timeframe=state['timeframe'], instrument=state['instrument'], candleClosedAt=closed_at))
        state.update(processedAt=closed_at, previousClose=close)
    return state, alerts, 'active'
