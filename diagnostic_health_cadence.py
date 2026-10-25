"""Passive, bounded analysis of archived health observation spacing.

Health journal messages are asynchronous and best-effort. An absent capture or
a long gap NEVER establishes a missed 30s market evaluation, an outage, a
market closure, or a defect in trading. No market or worker is invoked.
"""
import math
import re

SHA = re.compile(r"[a-f0-9]{40}\Z")
SESSIONS = frozenset(("trading", "preparation", "night", "weekend"))
MAX_ROWS = 20
GAP_REVIEW_SECONDS = 90


def _sample(event):
    if not isinstance(event, dict) or event.get("stage") != "health":
        return None
    t = event.get("observedAt")
    payload = event.get("payload")
    if type(t) not in (int, float) or not math.isfinite(t) or t <= 0 or not isinstance(payload, dict):
        return None
    session = payload.get("session")
    if not isinstance(session, str) or session not in SESSIONS:
        session = "unknown"
    sha = event.get("build")
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        sha = None
    return t, session, sha


def assess(events):
    """Only compare two consecutive captures with SAME known build and session."""
    if not isinstance(events, list):
        events = []
    observations = sorted(set(sample for e in events[:160]
                              if (sample := _sample(e)) is not None),
                          key=lambda item: item[0], reverse=True)[:MAX_ROWS]
    newest = observations[0] if observations else None
    intervals = []
    cross_boundaries = 0
    for after, before in zip(observations, observations[1:]):
        if (before[1] not in SESSIONS or before[1] != after[1] or before[2] is None or
                after[2] is None or before[2] != after[2]):
            cross_boundaries += 1
            continue
        gap = after[0] - before[0]
        if gap > 0:
            intervals.append((gap, after[1]))
    trading_intervals = [dt for dt, session in intervals if session == "trading"]
    other_intervals = [dt for dt, session in intervals if session != "trading"]
    long_trading = [dt for dt in trading_intervals if dt > GAP_REVIEW_SECONDS]
    latest_session = newest[1] if newest else "unknown"
    if not newest or not intervals:
        state = "insufficient-evidence"
    elif latest_session in ("weekend", "night", "preparation"):
        state = "outside-trading-window-observation"
    else:
        state = "sampled-health-capture-timing"
    return {
        "status": "observed" if intervals else "insufficient",
        "state": state,
        "readOnly": True,
        "realOrders": False,
        "sampledHealthCaptures": len(observations),
        "sameBuildSessionIntervals": len(intervals),
        "crossBuildOrSessionBoundariesSkipped": cross_boundaries,
        "observedTradingWindowIntervals": len(trading_intervals),
        "tradingCaptureIntervalsOver90s": len(long_trading),
        "maxTradingCaptureGapSeconds": (
            round(max(trading_intervals), 3) if trading_intervals else None),
        "observedNonTradingWindowIntervals": len(other_intervals),
        "latestCapturedAt": newest[0] if newest else None,
        "latestSession": latest_session,
        "workerMissed30sCyclesVerified": False,
        "workerStoppedVerified": False,
        "scope": "latest-20-passive-health-captures-only-not-market-worker-clock",
        "note": "Diagnostic delivery is asynchronous and lossy. A gap between captured "
                "health messages is only a review lead, not proof of missing 30-second "
                "market cycles, a stopped worker, an outage or a filled trade. "
                "Non-trading sessions and build transitions are kept separate.",
    }
