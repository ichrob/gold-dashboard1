"""Observe the repair loop independently; timestamps never manufacture progress."""
import threading
import time

_LOCK = threading.Lock()
_STARTED = time.monotonic()
_LAST = None


def completed(now=None):
    global _LAST
    with _LOCK:
        _LAST = time.monotonic() if now is None else now


def health(running, now=None):
    now = time.monotonic() if now is None else now
    with _LOCK:
        age = None if _LAST is None else max(0, now-_LAST)
        warmup = now-_STARTED < 150
    state = 'starting' if warmup and age is None else 'stopped' if not running else 'stalled' if age is None or age > 150 else 'ok'
    return dict(state=state, running=bool(running), lastCompletedAgeSeconds=age)
