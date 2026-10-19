"""One checked, immutable-by-copy Spot observation shared by all Bob consumers."""
import threading
import time
import logging
from datetime import datetime, timezone

URL = 'https://api.gold-api.com/price/XAU'
POLL_SECONDS = 30
_lock = threading.Lock()
_quote = None
_attempted = float('-inf')
_error = None
_route = 0
_retry_at = 0
ROUTES = (URL, URL + "/USD")


def current():
    global _quote, _attempted, _error, _route, _retry_at
    # Serialize provider access, including concurrent browser, monitor and model requests.
    with _lock:
        if time.monotonic() - _attempted >= POLL_SECONDS and time.monotonic() >= _retry_at:
            _attempted = time.monotonic()
            try:
                from product_quotes import issuer_json
                from future_estimate import parse_gold_api
                q = parse_gold_api(issuer_json(ROUTES[_route], 'https://api.gold-api.com/', timeout=10))
                age = (datetime.now(timezone.utc)-datetime.fromisoformat(q['at'])).total_seconds()
                if not 0 <= age <= 60:
                    raise ValueError('Spot-Kurs nicht aktuell')
                q['sourceUrl'] = ROUTES[_route]
                if _quote:
                    before = datetime.fromisoformat(_quote['at'])
                    after = datetime.fromisoformat(q['at'])
                    if after < before or (after == before and q['price'] != _quote['price']):
                        raise ValueError('Spot-Kurszeit rückläufig oder widersprüchlicher Kurs')
                if _error:
                    logging.info("BOB_MARKET_RECOVERY source=spot state=recovered")
                _quote, _error = q, None
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
                _error = type(exc).__name__
                # Equivalent documented USD route; one attempt per 30 seconds,
                # not a new provider or an invented source timestamp.
                code = getattr(exc, 'code', None)
                if code not in (401, 403, 429):
                    _route = 1-_route
                if code in (401, 403, 429):
                    delay = 300
                    raw = (getattr(exc, 'headers', None) or {}).get('Retry-After')
                    if raw:
                        try:
                            delay = max(delay, int(raw))
                        except ValueError:
                            try:
                                from email.utils import parsedate_to_datetime
                                delay = max(delay, (parsedate_to_datetime(raw)-datetime.now(timezone.utc)).total_seconds())
                            except (TypeError, ValueError):
                                pass
                    _retry_at = time.monotonic()+delay
                logging.warning("BOB_MARKET_RECOVERY source=spot state=retrying code=%s", _error)
        if not _quote or _error not in (None, 'OSError', 'URLError', 'TimeoutError', 'HTTPError'):
            raise ValueError('Gemeinsamer Spot-Abruf nicht verfügbar: ' + str(_error))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(_quote['at'])).total_seconds()
        if not 0 <= age <= 60:
            raise ValueError('Gemeinsamer Spot-Kurs veraltet oder Kurszeit zukünftig')
        return dict(_quote, refreshWarning='Letzter Abruf fehlgeschlagen; gespeicherter Kurs innerhalb 60 Sekunden' if _error else None)
