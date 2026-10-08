"""Independent, keyless XAU/USD broker candles; never substitutes the spot quote."""
import math
import threading
import time
from datetime import datetime

MINUTES = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240}
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
    """One request per minute, or 30 seconds for 1m; preserve source times."""
    with _locks[interval]:
        now = time.time()
        saved = _cache.get(interval)
        cache_seconds = 30 if interval == '1m' else 60
        if saved and now-saved[0] < cache_seconds:
            return [dict(b) for b in saved[1]]
        rows = saved[1] if saved else []
        try:
            payload = fetch_json(f'https://biquote.io/api/XAUUSD/ohlc?interval={interval}&limit=1000', retries=0, timeout=12)
            fresh = normalize(payload, interval)
            if fresh:
                rows = fresh
                closed = [b for b in rows if not b['isOpen']]
                last = closed[-1]['openTime'] if closed else 0
                print(f'BOB_CANDLES source=biquote interval={interval} count={len(rows)} last_closed={last} age_seconds={int(time.time()-last/1000)}', flush=True)
        except Exception as exc:
            print(f'BOB_CANDLES source=biquote interval={interval} unavailable={type(exc).__name__}', flush=True)
        _cache[interval] = (now, rows)
        return [dict(b) for b in rows]
