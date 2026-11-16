"""One bounded set of live-source workers across scanner refresh cycles.

Each named source has at most one outstanding task, including work still
running after the two-second secondary-source deadline. A slow provider cannot
create another nine worker threads every 30 seconds. Source clocks and Bob's
existing downstream freshness/identity gates stay authoritative.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

SOURCES = frozenset((
    "spot", "risk_spot_backup", "5m", "1h", "15m", "4h", "30m", "fx", "1m",
))


class BoundedSourceExecutor:
    """Fixed maximum worker count and no backlog for duplicate source work."""

    def __init__(self):
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=len(SOURCES),
                                        thread_name_prefix="bob-live")
        self._outstanding = {}

    def submit(self, source, action, *args):
        if source not in SOURCES:
            raise ValueError("Unknown live source")
        with self._lock:
            previous = self._outstanding.get(source)
            if previous is not None and not previous.done():
                # Reuse only this same source's active task. Returning its
                # original observation cannot create a newer provider clock.
                return previous
            future = self._pool.submit(action, *args)
            self._outstanding[source] = future
            return future

    def close(self):
        """Test/controlled shutdown; not used between production cycles."""
        self._pool.shutdown(wait=True, cancel_futures=True)


_SHARED = BoundedSourceExecutor()


def submit(source, action, *args):
    return _SHARED.submit(source, action, *args)
