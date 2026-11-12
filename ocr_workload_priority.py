"""Process-local admission for optional maintenance during handset OCR.

Never stops threads or transactions. Live quotes, positions and pushes do not
enter this gate. Freed allocator pages are reclaimed by the existing OCR guard.
"""
from contextlib import contextmanager
from functools import wraps
import threading

_CONDITION = threading.Condition()
_LOCAL = threading.local()
_BACKGROUND = 0
_OCR_WAITERS = 0
_OCR_ACTIVE = False


class OcrWorkloadDeferred(RuntimeError):
    pass


def status():
    with _CONDITION:
        return {'ocrActive': _OCR_ACTIVE, 'ocrWaiting': _OCR_WAITERS,
                'maintenanceRunning': _BACKGROUND,
                'maintenancePaused': _OCR_ACTIVE or _OCR_WAITERS > 0}


@contextmanager
def maintenance_slot():
    global _BACKGROUND
    if getattr(_LOCAL, 'maintenance', False):
        yield
        return
    with _CONDITION:
        _CONDITION.wait_for(lambda: not _OCR_ACTIVE and _OCR_WAITERS == 0)
        _BACKGROUND += 1
        _LOCAL.maintenance = True
    try:
        yield
    finally:
        with _CONDITION:
            _LOCAL.maintenance = False
            _BACKGROUND -= 1
            _CONDITION.notify_all()


def maintenance(function):
    @wraps(function)
    def run(*args, **kwargs):
        # Wait before opening connections or loading archive payloads. Preserve
        # the scheduled call, then resume it automatically when OCR exits.
        with maintenance_slot():
            return function(*args, **kwargs)
    return run


@contextmanager
def ocr_slot(timeout=15):
    global _OCR_ACTIVE, _OCR_WAITERS
    with _CONDITION:
        _OCR_WAITERS += 1
        try:
            if not _CONDITION.wait_for(lambda: _BACKGROUND == 0 and not _OCR_ACTIVE, timeout):
                raise OcrWorkloadDeferred('Maintenance still completing; OCR deferred')
            _OCR_ACTIVE = True
        finally:
            _OCR_WAITERS -= 1
            _CONDITION.notify_all()
    try:
        yield
    finally:
        with _CONDITION:
            _OCR_ACTIVE = False
            _CONDITION.notify_all()
