"""Bound product requests by ISIN, capacity and caller wait time."""
import copy
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='bob-product-source')
_LOCK = threading.Lock()
_PENDING = {}
WAIT_SECONDS = 25


def unavailable(isin, code):
    return dict(isin=isin,found=False,eligible=False,productVerified=False,sourceFailure=True,
                quoteFailureCode=code,reason='Produktabruf verzögert; gespeicherte Nachweise bleiben erhalten')


def run(isin, fetch):
    with _LOCK:
        for key, value in list(_PENDING.items()):
            if value.done(): _PENDING.pop(key, None)
        future = _PENDING.get(isin)
        if future is None:
            if len(_PENDING) >= 4:
                print('BOB_PRODUCT_RUNTIME capacity_exhausted',flush=True)
                return unavailable(isin,'PRODUCT_CAPACITY')
            future = _POOL.submit(fetch, isin)
            _PENDING[isin] = future
    try:
        return copy.deepcopy(future.result(timeout=WAIT_SECONDS))
    except TimeoutError:
        # Keep the running task registered: repeated refreshes cannot multiply it.
        print('BOB_PRODUCT_RUNTIME timeout',flush=True)
        return unavailable(isin,'PRODUCT_TIMEOUT')
    except Exception:
        print('BOB_PRODUCT_RUNTIME source_failed',flush=True)
        return unavailable(isin,'PRODUCT_SOURCE_FAILED')
