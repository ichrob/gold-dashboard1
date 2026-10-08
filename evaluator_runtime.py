"""Priority admission and in-flight deduplication; never cache completed decisions."""
import copy
import hashlib
import json
import subprocess
import threading
from time import monotonic

MAX_QUEUE_SECONDS = 10
_CONDITION = threading.Condition()
_WAITERS = []
_BUSY = False
_FLIGHTS = {}
_STATS = dict(completed=0, failed=0, queueTimeouts=0, shared=0, lastDurationMs=0, lastWaitMs=0)


def status():
    with _CONDITION:
        return dict(_STATS, busy=_BUSY, waiting=len(_WAITERS), inFlight=len(_FLIGHTS))


def run(args, priority=1, **kwargs):
    global _BUSY
    started = monotonic()
    # Include the full payload (trade settings, clocks and data) and process options.
    key = hashlib.sha256(repr((list(args), sorted(kwargs.items()))).encode()).digest()
    with _CONDITION:
        flight = _FLIGHTS.get(key)
        if flight is not None:
            _STATS['shared'] += 1
            if not _CONDITION.wait_for(lambda: flight['done'], MAX_QUEUE_SECONDS):
                _STATS['queueTimeouts'] += 1
                raise TimeoutError('Gemeinsame Analyse noch ausgelastet')
            if flight.get('error'): raise flight['error']
            return copy.deepcopy(flight['result'])
        flight = {'done': False}
        _FLIGHTS[key] = flight
        ticket = (priority, started, object())
        _WAITERS.append(ticket)
    acquired = False
    try:
        with _CONDITION:
            if not _CONDITION.wait_for(lambda: not _BUSY and ticket == min(_WAITERS, key=lambda t:t[:2]), MAX_QUEUE_SECONDS):
                _STATS['queueTimeouts'] += 1
                raise TimeoutError('Analyse ausgelastet; nächster Durchlauf erforderlich')
            _WAITERS.remove(ticket)
            _BUSY = acquired = True
        wait_ms = round((monotonic()-started)*1000)
        command = list(args)
        if command and command[0] == 'node': command.insert(1, '--v8-pool-size=1')
        result = subprocess.run(command, **kwargs)
        with _CONDITION:
            flight['result'] = result
            _STATS['failed' if getattr(result, 'returncode', 0) else 'completed'] += 1
        return result
    except BaseException as exc:
        with _CONDITION:
            flight['error'] = exc
            _STATS['failed'] += 1
        raise
    finally:
        with _CONDITION:
            if ticket in _WAITERS: _WAITERS.remove(ticket)
            if acquired: _BUSY = False
            flight['done'] = True
            _FLIGHTS.pop(key, None)
            _STATS['lastDurationMs'] = round((monotonic()-started)*1000)
            _STATS['lastWaitMs'] = locals().get('wait_ms', _STATS['lastDurationMs'])
            summary = dict(_STATS, priority=priority, waiting=len(_WAITERS))
            _CONDITION.notify_all()
        print('BOB_EVALUATOR '+json.dumps(summary), flush=True)
