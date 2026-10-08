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
WAIT_SECONDS = 25
MAX_PENDING = 16  # Four active workers plus a bounded queue for other products.
RESULT_TTL = 15   # Does not change any source timestamps.
ERROR_TTL = 30


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
                ttl = ERROR_TTL if result.get('sourceFailure') else RESULT_TTL
                _READY[key] = (now+ttl, copy.deepcopy(result))
                _READY.move_to_end(key)
                _PENDING.pop(key, None)
        for key, (expires, _) in list(_READY.items()):
            if expires <= now:
                _READY.pop(key, None)
        while len(_READY) > 256:
            _READY.popitem(last=False)
        cached = _READY.get(isin)
        if cached:
            return copy.deepcopy(cached[1])
        future = _PENDING.get(isin)
        if future is None:
            if len(_PENDING) >= MAX_PENDING:
                print('BOB_PRODUCT_RUNTIME capacity_exhausted',flush=True)
                return unavailable(isin,'PRODUCT_CAPACITY')
            future = _POOL.submit(fetch, isin)
            _PENDING[isin] = future
    try:
        return copy.deepcopy(future.result(timeout=WAIT_SECONDS))
    except TimeoutError:
        print('BOB_PRODUCT_RUNTIME timeout',flush=True)
        return unavailable(isin,'PRODUCT_TIMEOUT')
    except Exception:
        print('BOB_PRODUCT_RUNTIME source_failed',flush=True)
        return unavailable(isin,'PRODUCT_SOURCE_FAILED')
