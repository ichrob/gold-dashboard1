"""Isolate optional source failures; bounded retries, no invented evidence."""
import copy
import threading
import time
from collections import OrderedDict

STAGES = frozenset(('comdirect-fetch', 'swissquote-fetch', 'comdirect-terms',
                    'finanzen-terms', 'comdirect-quote', 'swissquote-quote'))
_LOCK = threading.Lock()
_FAILURES = OrderedDict()
_SOURCE_FAILURES = {}
_SOURCE_PAUSES = {}


def attempt(stage, isin, operation, fallback, events, *, now=None):
    if stage not in STAGES:
        raise ValueError('Unknown recovery stage')
    clock = time.monotonic() if now is None else now
    key = (stage, isin)
    with _LOCK:
        until = _SOURCE_PAUSES.get(stage, 0)
        if clock < until:
            events.append(dict(stage=stage, state="waiting", scope="source",
                               retryAfterSeconds=max(1, int(until-clock))))
            return copy.deepcopy(fallback)
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
            # Three distinct products failing the same adapter indicate a shared
            # fault. Keep other adapters available; never include ISINs in status.
            failures = {i:at for i,at in _SOURCE_FAILURES.get(stage, {}).items()
                        if 0 <= clock-at < 120}
            failures[isin] = clock
            _SOURCE_FAILURES[stage] = dict(list(failures.items())[-12:])
            if len(failures) >= 3:
                _SOURCE_PAUSES[stage] = clock+120
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
        _SOURCE_FAILURES.pop(stage, None)
        _SOURCE_PAUSES.pop(stage, None)
    if previous:
        # A successful call is not proof of complete/fresh product evidence.
        events.append(dict(stage=stage, state='call-restored', retryAfterSeconds=0))
    return result


def enrich(stage, isin, operation, original, events):
    # Failed enrichers cannot leave partly mutated evidence behind.
    def checked():
        candidate = operation(copy.deepcopy(original), isin)
        if not isinstance(candidate, dict):
            raise ValueError('Invalid enrichment')
        # Roll back the entire optional adapter mutation on identity corruption.
        # Original source timestamps remain original; fallback is never re-dated.
        if candidate.get('isin') not in (None, isin):
            raise ValueError('Changed product identity')
        if isinstance(original, dict) and original.get('isin') == isin and candidate.get('isin') != isin:
            raise ValueError('Lost product identity')
        return candidate
    return attempt(stage, isin, checked, original, events)


def health(now=None):
    clock = time.monotonic() if now is None else now
    with _LOCK:
        return {'pausedStages': sorted(stage for stage,until in _SOURCE_PAUSES.items() if until > clock),
                'pendingRetries': len(_FAILURES)}
