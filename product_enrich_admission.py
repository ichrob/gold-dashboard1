"""Bound concurrent product research before it occupies HTTP request threads.

The underlying quote runtime already bounds provider workers and unique queued
products.  Duplicate browser requests can still wait in separate HTTP threads,
however, so this small gate protects the scanner process and its health route.
"""
import threading


MAX_ACTIVE = 4
_GATE = threading.BoundedSemaphore(MAX_ACTIVE)


class ProductEnrichBusy(RuntimeError):
    """The existing bounded product-research capacity is in use."""


def run(loader):
    """Run one admitted read, or fail immediately without starting source work."""
    if not _GATE.acquire(blocking=False):
        raise ProductEnrichBusy("Product research capacity in use")
    try:
        return loader()
    finally:
        _GATE.release()
