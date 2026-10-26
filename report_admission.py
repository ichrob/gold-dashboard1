"""Bound expensive report reads before acquiring a database connection.

Only overlapping identical reads share work; no completed result is cached.
Callers must authenticate before admission. Writes never enter this gate.
"""
import copy
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError

_lock=threading.Lock()
_pending={}
_slots=threading.BoundedSemaphore(2)
_ACTIVE_LOADS=0
_COUNTERS=dict(completed=0, failed=0, capacityTimeouts=0,
               queueFull=0, joined=0, joiningTimeouts=0)


def status():
    """Small process-local counters only; never disclose report keys/payloads."""
    with _lock:
        return dict(status='observed', readOnly=True, realOrders=False,
                    scope='push-process-read-report-admission-since-start',
                    pendingKeys=len(_pending), activeLoads=_ACTIVE_LOADS,
                    maxActiveLoads=2, maxPendingKeys=32, **_COUNTERS)



def read(key, loader):
    global _ACTIVE_LOADS
    with _lock:
        future=_pending.get(key)
        owner=future is None
        if owner:
            if len(_pending)>=32:
                _COUNTERS['queueFull']+=1
                raise TimeoutError('Report queue full')
            future=Future()
            _pending[key]=future
    if not owner:
        with _lock:_COUNTERS['joined']+=1
        try:
            return copy.deepcopy(future.result(timeout=40))
        except FutureTimeoutError:
            # An owner's completed TimeoutError is NOT a follower wait timeout.
            if not future.done():
                with _lock:_COUNTERS['joiningTimeouts']+=1
            raise
    admitted=False
    try:
        admitted=_slots.acquire(timeout=30)
        if not admitted:
            with _lock:_COUNTERS['capacityTimeouts']+=1
            raise TimeoutError('Report capacity unavailable')
        with _lock:_ACTIVE_LOADS+=1
        result=loader()  # Only now may the loader borrow a database connection.
        # Prepare the owner response before publishing success to waiting reads.
        # A copy failure must complete the shared future with that error once.
        response=copy.deepcopy(result)
        future.set_result(result)
        with _lock:_COUNTERS['completed']+=1
        return response
    except BaseException as exc:
        with _lock:_COUNTERS['failed']+=1
        future.set_exception(exc)
        raise
    finally:
        if admitted:_slots.release()
        with _lock:
            if admitted:_ACTIVE_LOADS-=1
            _pending.pop(key,None)
