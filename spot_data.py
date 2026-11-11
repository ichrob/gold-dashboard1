"""One checked, immutable-by-copy Spot observation shared by all Bob consumers."""
import threading
import time
import logging
from datetime import datetime, timezone

URL = 'https://api.gold-api.com/price/XAU'
POLL_SECONDS = 30
NEAR_EXPIRY_SECONDS = 30  # Original quote age, not time since the HTTP request.
NEAR_EXPIRY_RETRY_SECONDS = 5
_lock = threading.Lock()
_quote = None
_attempted = float('-inf')
_error = None
_route = 0
_retry_at = 0
_near_expiry_retried_at = None
ROUTES = (URL, URL + "/USD")


def _poll_interval():
    """Refresh ageing observations at the 30s cadence, without changing their clock."""
    if not _quote or _quote.get('at') == _near_expiry_retried_at:
        return POLL_SECONDS
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(_quote['at'])).total_seconds()
    except (KeyError, TypeError, ValueError, AttributeError):
        return POLL_SECONDS
    return NEAR_EXPIRY_RETRY_SECONDS if age >= NEAR_EXPIRY_SECONDS else POLL_SECONDS


def _cached_observation():
    # The quote dictionary is replaced, never mutated after publication.
    # A concurrent refresh must not make readers wait on its network lock.
    quote,error=_quote,_error
    if not quote or error not in (None,'OSError','URLError','TimeoutError','HTTPError'):
        raise ValueError('Gemeinsamer Spot-Abruf nicht verfügbar: '+str(error))
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(quote['at'])).total_seconds()
    if not 0<=age<=60:
        raise ValueError('Gemeinsamer Spot-Kurs veraltet oder Kurszeit zukünftig')
    return dict(quote,refreshWarning='Letzter Abruf fehlgeschlagen; gespeicherter Kurs innerhalb 60 Sekunden' if error else None)


def primary(blocking=True):
    global _quote, _attempted, _error, _route, _retry_at, _near_expiry_retried_at
    # Serialize provider access, including concurrent browser, monitor and model requests.
    if not _lock.acquire(blocking=blocking):
        return _cached_observation()
    try:
        now_monotonic = time.monotonic()
        poll_interval = _poll_interval()
        if now_monotonic - _attempted >= poll_interval and now_monotonic >= _retry_at:
            _attempted = now_monotonic
            previous_at = (_quote or {}).get('at')
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
                # Prospective source-clock evidence only: no price, product or
                # account data. This distinguishes a provider-repeated original
                # timestamp from a Bob handoff delay without changing polling.
                print(
                    "BOB_SPOT_FETCH_EVIDENCE source_at=%s age_ms=%d repeated=%s early_retry=%s route=%d"
                    % (q['at'], int(round(age * 1000)), q['at'] == previous_at,
                       poll_interval == NEAR_EXPIRY_RETRY_SECONDS, _route),
                    flush=True,
                )
                if _error:
                    logging.info("BOB_MARKET_RECOVERY source=spot state=recovered")
                # A provider observation first received close to expiry gets one
                # bounded early retry. If the provider repeats the same original
                # time, resume the normal cadence instead of polling repeatedly.
                _near_expiry_retried_at = q['at'] if q['at'] == previous_at and age >= NEAR_EXPIRY_SECONDS else None
                _quote, _error = q, None
            except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
                _error = type(exc).__name__
                if previous_at and poll_interval == NEAR_EXPIRY_RETRY_SECONDS:
                    _near_expiry_retried_at = previous_at
                # Failed requests have no verified new provider clock. Emit
                # fixed, price-free attempt context to compare retry timing
                # with separate original-study witnesses (never the raw error).
                print(
                    "BOB_SPOT_FETCH_FAILURE reason=%s early_retry=%s attempted_route=%d"
                    % (_error, poll_interval == NEAR_EXPIRY_RETRY_SECONDS, _route),
                    flush=True,
                )
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
        return _cached_observation()
    finally:
        _lock.release()



def current():
    """Shared original/standby selection for every generic spot consumer.

    The backup is warmed independently; fallback never starts blocking I/O.
    Models tied to a specific provider must still validate that identity.
    """
    try:
        return primary(blocking=False)
    except (OSError, ValueError, KeyError, TypeError):
        from xaus_spot import peek
        backup = peek()
        if backup is None:
            # Cold start: if no checked source exists, wait for the single
            # running provider call rather than starting another request.
            if _lock.locked():
                return primary()
            raise
        return dict(backup, underlying='XAU/USD', proxyKind='xaus-spot',
                    backupActive=True, refreshWarning='Hauptquelle nicht verfügbar; geprüfte XAUS-Ersatzquelle')
