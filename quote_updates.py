"""Coalesced in-process notifications for already completed source work.

No network calls, price substitution, workers, or changes to source clocks.
"""
import threading
import time


class QuoteUpdates:
    def __init__(self, minimum_interval=10):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._interest = set()
        self._last_wake = float('-inf')
        self.minimum_interval = minimum_interval

    def track(self, isins):
        with self._lock:
            self._interest = set(isins)

    def notify(self, isin):
        with self._lock:
            interested = isin in self._interest
        if interested:
            self._event.set()

    def set(self):
        self._event.set()

    def clear(self):
        self._event.clear()

    def wait(self, timeout=None):
        ready = self._event.wait(timeout)
        # One existing simulation worker consumes a burst together; completing
        # ten quotes must not create ten database/evaluator cycles at once.
        remaining = self.minimum_interval - (time.monotonic() - self._last_wake)
        if remaining > 0:
            time.sleep(remaining)
        self._last_wake = time.monotonic()
        return ready


updates = QuoteUpdates()


def completed(isin, future):
    if future.cancelled():
        return
    try:
        result = future.result()
    except Exception:
        return
    if isinstance(result, dict) and result.get('isin') == isin and not result.get('sourceFailure'):
        updates.notify(isin)
