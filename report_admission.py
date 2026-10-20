"""Bound expensive report reads before acquiring a database connection.

Only overlapping identical reads share work; no completed result is cached.
Callers must authenticate before admission. Writes never enter this gate.
"""
import copy
import threading
from concurrent.futures import Future

_lock=threading.Lock()
_pending={}
_slots=threading.BoundedSemaphore(2)


def read(key, loader):
    with _lock:
        future=_pending.get(key)
        owner=future is None
        if owner:
            if len(_pending)>=32:raise TimeoutError('Report queue full')
            future=Future()
            _pending[key]=future
    if not owner:return copy.deepcopy(future.result(timeout=40))
    admitted=False
    try:
        admitted=_slots.acquire(timeout=30)
        if not admitted:raise TimeoutError('Report capacity unavailable')
        result=loader()  # Only now may the loader borrow a database connection.
        future.set_result(result)
        return copy.deepcopy(result)
    except BaseException as exc:
        future.set_exception(exc)
        raise
    finally:
        if admitted:_slots.release()
        with _lock:_pending.pop(key,None)
