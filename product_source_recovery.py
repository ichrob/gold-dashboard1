"""Isolate optional source failures; bounded retries, no invented evidence."""
import copy
import threading
import time
from collections import OrderedDict

STAGES = frozenset(('comdirect-fetch', 'swissquote-fetch', 'comdirect-terms',
                    'finanzen-terms', 'comdirect-quote', 'swissquote-quote'))
_LOCK = threading.Lock()
_FAILURES = OrderedDict()


def attempt(stage, isin, operation, fallback, events, *, now=None):
    if stage not in STAGES:
        raise ValueError('Unknown recovery stage')
    clock = time.monotonic() if now is None else now
    key = (stage, isin)
    with _LOCK:
        previous = _FAILURES.get(key)
        if previous and clock < previous['next']:
            events.append(dict(stage=stage, state='waiting',
                               retryAfterSeconds=max(1, int(previous['next']-clock))))
            return copy.deepcopy(fallback)
    try:
        result = operation()
        if not isinstance(result, dict):
            raise ValueError('Invalid source result')
    except Exception:
        # No exception text, credentials, quote values or external instructions.
        with _LOCK:
            count = min(5, (previous or {}).get('count', 0)+1)
            delay = min(300, 30*2**(count-1))
            _FAILURES[key] = dict(count=count, next=clock+delay)
            _FAILURES.move_to_end(key)
            while len(_FAILURES)>256:
                _FAILURES.popitem(last=False)
        events.append(dict(stage=stage, state='failed', retryAfterSeconds=delay))
        return copy.deepcopy(fallback)
    with _LOCK:
        _FAILURES.pop(key, None)
    if previous:
        # A successful call is not proof of complete/fresh product evidence.
        events.append(dict(stage=stage, state='call-restored', retryAfterSeconds=0))
    return result


def enrich(stage, isin, operation, original, events):
    # Failed enrichers cannot leave partly mutated evidence behind.
    return attempt(stage, isin, lambda: operation(copy.deepcopy(original), isin), original, events)
