"""One checked, immutable-by-copy Spot observation shared by all Bob consumers."""
import threading
import time
from datetime import datetime, timezone

URL = 'https://api.gold-api.com/price/XAU'
POLL_SECONDS = 30
_lock = threading.Lock()
_quote = None
_attempted = float('-inf')
_error = None


def current():
    global _quote, _attempted, _error
    # Serialize provider access, including concurrent browser, monitor and model requests.
    with _lock:
        if time.monotonic() - _attempted >= POLL_SECONDS:
            _attempted = time.monotonic()
            try:
                from product_quotes import issuer_json
                from future_estimate import parse_gold_api
                q = parse_gold_api(issuer_json(URL, 'https://api.gold-api.com/', timeout=10))
                if _quote:
                    before = datetime.fromisoformat(_quote['at'])
                    after = datetime.fromisoformat(q['at'])
                    if after < before or (after == before and q['price'] != _quote['price']):
                        raise ValueError('Spot-Kurszeit rückläufig oder widersprüchlicher Kurs')
                _quote, _error = q, None
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
                _error = type(exc).__name__
        if _error or not _quote:
            raise ValueError('Gemeinsamer Spot-Abruf nicht verfügbar: ' + str(_error))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(_quote['at'])).total_seconds()
        if not 0 <= age <= 60:
            raise ValueError('Gemeinsamer Spot-Kurs veraltet oder Kurszeit zukünftig')
        return dict(_quote)
