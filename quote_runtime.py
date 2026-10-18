"""Bound concurrent source work; retain completed results after caller timeouts."""
import copy
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='bob-product-source')
_LOCK = threading.Lock()
_PENDING = {}
_READY = OrderedDict()
_FAILURES = OrderedDict()
# Verified source evidence is kept separately from the short live-result cache.
# A 30-second caller must not lose a successful result completed after its timeout.
_RETAINED = OrderedDict()
RETENTION_SECONDS = 8 * 3600
WAIT_SECONDS = 25
MAX_PENDING = 16  # Four active workers plus a bounded queue for other products.
RESULT_TTL = 15   # Does not change any source timestamps.
ERROR_TTL = 30


def _remember_verified(isin, result, completed_at):
    """Keep observed original clocks; never manufacture a fresh observation."""
    if (not isinstance(result, dict) or result.get('isin') != isin
            or result.get('productVerified') is not True
            or result.get('sourceFailure') is True
            or (result.get('metadata') or {}).get('status') not in (1, 2)):
        return
    _RETAINED[isin] = (completed_at, copy.deepcopy(result))
    _RETAINED.move_to_end(isin)
    while len(_RETAINED) > 256:
        _RETAINED.popitem(last=False)


def _unavailable_with_evidence(isin, code, now):
    """Historical terms may remain visible, but none are live/tradable."""
    saved = _RETAINED.get(isin)
    if saved is None or not 0 <= now - saved[0] <= RETENTION_SECONDS:
        _RETAINED.pop(isin, None)
        return unavailable(isin, code)
    result = copy.deepcopy(saved[1])
    result.update(found=False, fresh=False, eligible=False,
                  isExecutableQuote=False, degiroExecutable=False,
                  sourceFailure=True, quoteFailureCode=code,
                  retainedAfterSourceFailure=True, retryAfterSeconds=30,
                  reason='Produktquelle vorübergehend nicht erreichbar; letzte bestätigte Angaben nur historisch mit Originalzeit, keine Kurs- oder Handelsfreigabe')
    return result


def unavailable(isin, code):
    return dict(isin=isin,found=False,eligible=False,productVerified=False,sourceFailure=True,
                quoteFailureCode=code,retryAfterSeconds=30,
                reason='Produktabruf verzögert; gespeicherte Nachweise bleiben erhalten')


def run(isin, fetch):
    with _LOCK:
        now = time.monotonic()
        # Harvest before removal: a timed-out caller must not lose the eventual result.
        for key, value in list(_PENDING.items()):
            if value.done():
                try:
                    result = value.result()
                except Exception:
                    result = unavailable(key, 'PRODUCT_SOURCE_FAILED')
                # Save valid evidence even when its 15s fast-cache slot expired
                # while Bob waited for the next 30s refresh.
                completed_at = getattr(value, '_bob_completed_at', now)
                _remember_verified(key, result, completed_at)
                if result.get('sourceFailure'):
                    failures=min(5,_FAILURES.get(key,0)+1)
                    _FAILURES[key]=failures;_FAILURES.move_to_end(key)
                    ttl=min(300,ERROR_TTL*2**(failures-1))
                    result=dict(result,retryAfterSeconds=ttl)
                else:
                    _FAILURES.pop(key,None)
                    ttl=RESULT_TTL
                while len(_FAILURES)>256:_FAILURES.popitem(last=False)
                # Age starts when source work finishes, not when another
                # request happens to collect it (possibly hours later).
                expires = completed_at + ttl
                if expires > now:
                    _READY[key] = (expires, copy.deepcopy(result))
                    _READY.move_to_end(key)
                _PENDING.pop(key, None)
        for key, (expires, _) in list(_READY.items()):
            if expires <= now:
                _READY.pop(key, None)
        while len(_READY) > 256:
            _READY.popitem(last=False)
        cached = _READY.get(isin)
        if cached:
            output = copy.deepcopy(cached[1])
            if output.get('sourceFailure') is True and output.get('productVerified') is not True:
                result=_unavailable_with_evidence(isin, output.get('quoteFailureCode') or 'PRODUCT_SOURCE_FAILED', now)
                result['retryAfterSeconds']=max(1,int(cached[0]-now))
                return result
            return output
        future = _PENDING.get(isin)
        if future is None:
            if len(_PENDING) >= MAX_PENDING:
                print('BOB_PRODUCT_RUNTIME capacity_exhausted',flush=True)
                return _unavailable_with_evidence(isin, 'PRODUCT_CAPACITY', now)
            future = _POOL.submit(fetch, isin)
            future.add_done_callback(lambda done: setattr(done, '_bob_completed_at', time.monotonic()))
            _PENDING[isin] = future
    try:
        result = copy.deepcopy(future.result(timeout=WAIT_SECONDS))
        with _LOCK:
            now = time.monotonic()
            _remember_verified(isin, result, getattr(future, '_bob_completed_at', now))
            if result.get('sourceFailure') is True and result.get('productVerified') is not True:
                return _unavailable_with_evidence(isin, result.get('quoteFailureCode') or 'PRODUCT_SOURCE_FAILED', now)
        return result
    except TimeoutError:
        print('BOB_PRODUCT_RUNTIME timeout',flush=True)
        with _LOCK:
            return _unavailable_with_evidence(isin, 'PRODUCT_TIMEOUT', time.monotonic())
    except Exception:
        print('BOB_PRODUCT_RUNTIME source_failed',flush=True)
        with _LOCK:
            return _unavailable_with_evidence(isin, 'PRODUCT_SOURCE_FAILED', time.monotonic())
