"""Independent, keyless XAU/USD broker candles; never substitutes the spot quote."""
import candle_reliability
import math
import threading
import time
from datetime import datetime

MINUTES = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240}
_cache = {}
_locks = {tf: threading.Lock() for tf in MINUTES}


def normalize(payload, interval, now=None):
    now = time.time() if now is None else now
    if not isinstance(payload, dict) or payload.get('symbol') != 'XAUUSD' or payload.get('interval') != interval:
        return []
    rows = {}
    step = MINUTES[interval] * 60000
    for raw in payload.get('bars', []):
        try:
            stamp = datetime.fromisoformat(raw['openTime'].replace('Z', '+00:00'))
            ts = stamp.timestamp() * 1000
            prices = [raw[k] for k in ('open', 'high', 'low', 'close')]
            if (stamp.tzinfo is None or ts <= 0 or ts > now*1000 or ts % step or
                    any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v <= 0 for v in prices) or
                    not isinstance(raw.get('isOpen'), bool)):
                return []
            o, h, low, c = prices
            if low > min(o, c) or h < max(o, c) or ts in rows:
                return []
            rows[ts] = dict(openTime=int(ts), open=o, high=h, low=low, close=c,
                            isOpen=raw['isOpen'] or now*1000 < ts+step,
                            providerIsOpen=raw['isOpen'], instrument='XAU/USD',
                            source='biquote · XAU/USD Broker/MT5')
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            return []
    return [rows[ts] for ts in sorted(rows)]


def fetch(interval, fetch_json):
    """Use source-provided candles only; briefly poll a new 15m close faster.

    At most one request per 30 seconds in the first 90 seconds following
    a 15m boundary. Normal 15m polling stays at 60 seconds. This shortens
    cache-induced delays but cannot accelerate the upstream publisher.
    """
    with _locks[interval]:
        now = time.time()
        saved = _cache.get(interval)
        near_15m_close = interval == '15m' and 0 <= now % 900 < 90
        cache_seconds = 30 if interval in ('1m', '5m') or near_15m_close else 60
        if saved and now-saved[0] < cache_seconds:
            return [dict(b) for b in saved[1]]
        rows = saved[1] if saved else []
        try:
            payload = fetch_json(f'https://biquote.io/api/XAUUSD/ohlc?interval={interval}&limit=1000', retries=0, timeout=12)
            fresh = normalize(payload, interval)
            candle_reliability.observe('biquote',interval,fresh)
            # A lagging upstream replica must not replace a newer confirmed
            # snapshot. Equal-clock corrections remain accepted.
            newest_closed = lambda values: max((b['openTime'] for b in values
                if not b['isOpen'] and not b.get('providerIsOpen')), default=0)
            if fresh and newest_closed(fresh) < newest_closed(rows):
                print(f'BOB_CANDLES source=biquote interval={interval} ignored=regressing-snapshot', flush=True)
                fresh = []
            if fresh:
                # Retain older, provider-confirmed candles as the upstream
                # rolling window advances. Never close a candle locally or
                # splice old values into a gap inside the fresh response.
                first = fresh[0]['openTime']
                older = [b for b in rows if b['openTime'] < first
                         and not b['isOpen'] and not b.get('providerIsOpen')]
                rows = (older + fresh)[-1000:]
                closed = [b for b in rows if not b['isOpen']]
                last = closed[-1]['openTime'] if closed else 0
                print(f'BOB_CANDLES source=biquote interval={interval} count={len(rows)} last_closed={last} age_seconds={int(time.time()-last/1000)}', flush=True)
        except Exception as exc:
            candle_reliability.observe('biquote',interval,error='unavailable')
            print(f'BOB_CANDLES source=biquote interval={interval} unavailable={type(exc).__name__}', flush=True)
        _cache[interval] = (now, rows)
        return [dict(b) for b in rows]
