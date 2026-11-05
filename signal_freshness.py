"""Bounded freshness observations; no fetches, workers or trading decisions."""
from datetime import datetime
import math
import time


def snapshot(areas, now=None):
    now = time.time() if now is None else now
    market = areas.get('market') or {}
    background = areas.get('background') or {}
    session = market.get('sessionMode')
    # A live position keeps the existing background cadence at 30s at night.
    monitoring = (session in ('trading', 'preparation') or
                  (session == 'night' and background.get('expectedCycleSeconds') == 30))

    def clock(value, unit='seconds'):
        if unit == 'iso':
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                value = parsed.timestamp() if parsed.tzinfo is not None else None
            except (AttributeError, TypeError, ValueError, OverflowError):
                value = None
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            return None
        return value / 1000 if unit == 'ms' else value

    def observation(value, unit='seconds'):
        at = clock(value, unit)
        age = now - at if at is not None else None
        state = ('unavailable' if age is None or age < 0 else
                 'stale' if monitoring and age > 120 else
                 'degraded' if monitoring and age > 60 else 'observed')
        return {'status': state, 'sourceAt': at,
                'ageSeconds': round(age, 3) if age is not None and age >= 0 else None,
                'within60Seconds': age is not None and 0 <= age <= 60}

    source = observation((market.get('source') or {}).get('spot_price_as_of'), 'iso')
    frames = (areas.get('analysis') or {}).get('timeframes') or {}
    analyses = {}
    for tf in ('1m', '5m', '15m', '30m', '1h'):
        if tf not in frames:
            continue
        result = (frames[tf] or {}).get('result') or {}
        analyses[tf] = {'input': observation(result.get('dataAt'), 'ms'),
                        'completed': observation(result.get('analysisCompletedAt'), 'ms')}
    heartbeat = observation(background.get('lastSuccessAt'))
    observations = [source, heartbeat] + [item for frame in analyses.values() for item in frame.values()]
    states = {item['status'] for item in observations}
    status = ('stale' if 'stale' in states else 'degraded' if 'degraded' in states else
              'unavailable' if 'unavailable' in states or not analyses or session is None else 'observed')
    # Delay statistics are only a sample of actually acknowledged messages.
    # Missing receipts and TEST traffic cannot be treated as fast delivery.
    deliveries = areas.get('pushDeliveries') or {}
    records = deliveries.get('records') or []
    delays = []
    eligible = 0
    for record in records[:100]:
        if (record.get('test') is not False or record.get('synthetic') is not False
                or record.get('outcome') != 'provider-accepted'):
            continue
        eligible += 1
        delay = (record.get('latency') or {}).get('sourceToBrowserReceiptMs')
        if type(delay) in (int, float) and math.isfinite(delay) and delay >= 0:
            delays.append(delay)
    return {'status': status, 'readOnly': True, 'sessionMode': session,
            'timelinessExpected': monitoring, 'targetCycleSeconds': 30,
            'warningAfterSeconds': 60, 'staleAfterSeconds': 120,
            'marketSource': source, 'analysis': analyses, 'background': heartbeat,
            'pushSample': {'providerAccepted': eligible, 'timedBrowserReceipts': len(delays),
                'missingTiming': eligible - len(delays),
                'over60Seconds': sum(delay > 60000 for delay in delays),
                'maxSeconds': round(max(delays)/1000, 3) if delays else None,
                'scope': 'bounded-sample-server-receipt-not-Android-display'},
            'scope': 'original-clock-observations-not-trade-approval',
            'note': 'Off-hours ages remain visible; no source clocks are rewritten. '
                    'Thresholds monitor timing and do not change entry or KO rules.'}
