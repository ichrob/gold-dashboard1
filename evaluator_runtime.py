"""Bounded shared CPU admission for analysis, product checks and paper trials."""
import subprocess
import threading

_SLOT = threading.BoundedSemaphore(1)
MAX_QUEUE_SECONDS = 10


def run(args, **kwargs):
    if not _SLOT.acquire(timeout=MAX_QUEUE_SECONDS):
        raise TimeoutError('Analyse ausgelastet; nächster regulärer Durchlauf erforderlich')
    try:
        # The child evaluates freshness after waiting, using original source clocks.
        # Limit V8 helper threads on the shared free instance; do not cache results.
        command = list(args)
        if command and command[0] == 'node':
            command.insert(1, '--v8-pool-size=1')
        return subprocess.run(command, **kwargs)
    finally:
        _SLOT.release()
