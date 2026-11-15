"""Bounded offline screen-observation replay. No browser/phone/network driver.

Inputs are normalized observations, not screenshots and not executable quotes.
Action proposals are descriptive only and must never be sent to a live driver.
"""
from math import isfinite


def replay(frames, expected_isin, *, max_age_seconds=30):
    if (type(frames) is not list or not 1 <= len(frames) <= 20
            or not isinstance(expected_isin, str) or not expected_isin
            or type(max_age_seconds) not in (int, float)
            or not isfinite(max_age_seconds) or not 0 < max_age_seconds <= 30):
        raise ValueError('Invalid bounded replay input')
    journal, seen = [], set()
    phase, last_time = 'SEARCH', None

    def result(code):
        return dict(mode='OFFLINE_SCREEN_REPLAY', code=code, journal=journal,
                    brokerConnected=False, liveOrdersEnabled=False,
                    actionsExecuted=0, isExecutableQuote=False,
                    recognitionVerified=False)

    for frame in frames:
        if type(frame) is not dict:
            return result('INVALID_FRAME')
        # Explicit absence is required; missing detector output is not clearance.
        if frame.get('challenge') is not False:
            return result('CHALLENGE_OR_UNKNOWN')
        if frame.get('screen') in ('LOGIN', 'ORDER', 'CONFIRMATION'):
            return result('PROTECTED_SCREEN')
        identity, observed, received = (frame.get(k) for k in
                                       ('frameId', 'observedAt', 'receivedAt'))
        if not isinstance(identity, str) or not identity:
            return result('INVALID_FRAME')
        if identity in seen:
            return result('REPEATED_FRAME')
        seen.add(identity)
        if any(type(t) not in (int, float) or not isfinite(t)
               for t in (observed, received)):
            return result('INVALID_TIME')
        if not 0 <= received - observed <= max_age_seconds:
            return result('STALE_OR_FUTURE_FRAME')
        if last_time is not None and observed <= last_time:
            return result('NON_MONOTONIC_FRAME')
        last_time = observed
        screen = frame.get('screen')
        if screen != phase:
            return result('UNEXPECTED_SCREEN')
        if phase == 'SEARCH':
            # Exact, unique identity. Never guess the first search result.
            candidates = frame.get('candidates')
            if (type(candidates) is not list or not 1 <= len(candidates) <= 100
                    or any(not isinstance(item, str) or not item for item in candidates)
                    or candidates.count(expected_isin) != 1):
                return result('AMBIGUOUS_IDENTITY')
            journal.append(dict(step='WOULD_OPEN_PRODUCT', executed=False))
            phase = 'DETAIL'
        elif phase == 'DETAIL':
            if frame.get('isin') != expected_isin:
                return result('IDENTITY_MISMATCH')
            if frame.get('currency') not in ('EUR', 'CHF'):
                return result('INVALID_CURRENCY')
            bid, ask = frame.get('bid'), frame.get('ask')
            if (any(type(v) not in (int, float) or not isfinite(v)
                    for v in (bid, ask)) or not 0 < bid <= ask):
                return result('INVALID_QUOTES')
            journal.append(dict(step='WOULD_CAPTURE_OBSERVATION', executed=False))
            phase = 'DONE'
    return result('OBSERVATION_ACCEPTED_OFFLINE' if phase == 'DONE' else 'INCOMPLETE')


def demonstration():
    """Synthetic fixture only; no private product/account data."""
    return replay([
        dict(frameId='fixture-1', screen='SEARCH', challenge=False,
             observedAt=100, receivedAt=101, candidates=['SYNTHETIC']),
        dict(frameId='fixture-2', screen='DETAIL', challenge=False,
             observedAt=102, receivedAt=103, isin='SYNTHETIC',
             currency='EUR', bid=1.0, ask=1.02),
    ], 'SYNTHETIC')
