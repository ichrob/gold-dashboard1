"""Bounded observed XAUS spot fallback for the independent risk paper study."""
import math
import threading
import time
from datetime import datetime, timezone

URL = 'https://xaus.com/api/v1/spot?compact=1&currency=USD&unit=oz'
_lock = threading.Lock()
_attempted = float('-inf')
_retry_at = 0
_quote = None

def parse(payload, now=None):
    now = time.time() if now is None else now
    xau = payload['xau']; state = payload['data_state']
    price = xau['price']
    if (xau.get('currency') != 'USD' or xau.get('unit') != 'oz'
            or type(price) not in (int, float) or not math.isfinite(price) or price <= 0
            or price != payload.get('spot_usd_oz') or state.get('status') != 'fresh'
            or state.get('source') != 'upstream'):
        raise ValueError('XAUS identity or original observation not confirmed')
    at = datetime.fromisoformat(state['as_of'].replace('Z', '+00:00'))
    published = datetime.fromisoformat(payload['updated_at'].replace('Z', '+00:00'))
    if (at.tzinfo is None or published.tzinfo is None
            or not at.timestamp() <= published.timestamp() <= now
            or not 0 <= now-at.timestamp() <= 60):
        raise ValueError('XAUS source clock unavailable or stale')
    return dict(price=price, at=at.astimezone(timezone.utc).isoformat(), source='XAUS · XAU/USD Spot',
                sourceUrl=URL, instrument='XAU/USD', observed=True)

def current(fetch_json=None):
    global _attempted, _retry_at, _quote
    with _lock:
        clock = time.monotonic()
        if clock-_attempted >= 30 and clock >= _retry_at:
            _attempted = clock
            try:
                from product_quotes import issuer_json
                payload = (fetch_json(URL, retries=0, timeout=2) if fetch_json is not None
                           else issuer_json(URL, 'https://xaus.com/', timeout=2))
                quote = parse(payload)
                if _quote and (quote['at'] < _quote['at'] or
                        (quote['at'] == _quote['at'] and quote['price'] != _quote['price'])):
                    raise ValueError('XAUS source clock regressed or conflicts')
                _quote = quote
            except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
                if getattr(exc, 'code', None) in (401, 403, 429):
                    delay = 300
                    raw = (getattr(exc, 'headers', None) or {}).get('Retry-After')
                    try:
                        delay = max(delay, int(raw))
                    except (TypeError, ValueError):
                        try:
                            from email.utils import parsedate_to_datetime
                            delay = max(delay, parsedate_to_datetime(raw).timestamp()-time.time())
                        except (TypeError, ValueError, AttributeError):
                            pass
                    _retry_at = time.monotonic()+delay
                _quote = None
        if not _quote or not 0 <= time.time()-datetime.fromisoformat(_quote['at']).timestamp() <= 60:
            return None
        return dict(_quote)
