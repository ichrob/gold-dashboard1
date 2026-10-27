"""Read-only evidence of data actually passed into Bob's paper-account evaluations.

Never store prices, ISINs, balances, order parameters, device data or secrets.
Source clocks stay original. An observed worker input cannot prove an exit
or the availability of an executable issuer/broker bid.
"""
import math
import time
from decimal import Decimal
from paper_gap_archive import _times, WINDOW_MS, RETENTION_MS, MAX_EVENTS
import diagnostic_history

_ALLOWED_PROFILES = frozenset(("conservative", "balanced", "offensive", "early100", "trend800", "early1000oct", "normal1000oct"))
_FIELDS = ("profile", "outcome", "ready", "priceFresh", "dataAt", "barAt")


def _ms(v):
    return v if type(v) in (int, float) and math.isfinite(v) and v > 0 else None


def sanitized_profile(profile, market, outcome):
    if profile not in _ALLOWED_PROFILES:
        return None
    market = market if isinstance(market, dict) else {}
    return {
        "profile": profile,
        "outcome": "checked" if outcome == "checked" else "evaluation-error",
        "ready": market.get("ready") is True,
        "priceFresh": market.get("priceFresh") is True,
        "dataAt": _ms(market.get("dataAt")),
        "barAt": _ms(market.get("analysisBarAt")),
    }


def capture(bundle, profile_observations, committed_at=None):
    """Enqueue only AFTER the paper ledger's DB transaction has committed.

    No extra work in the trading/quote/portfolio transaction, and a failed
    audit must not delay or modify the paper worker.
    """
    values = []
    for row in profile_observations[:len(_ALLOWED_PROFILES)] if isinstance(profile_observations, list) else []:
        if not isinstance(row, dict):
            continue
        name = row.get("profile")
        if name not in _ALLOWED_PROFILES:
            continue
        values.append({k: row.get(k) for k in _FIELDS})
    if not values:
        return False
    diagnostic_history.emit(
        "paper-input", diagnostic_history.trace(bundle),
        {"profiles": values, "phase": "post-commit",
         "checkedAt": _ms(committed_at) or int(time.time() * 1000)})
    return True


_SQL = """SELECT observed_at, payload FROM bob_diagnostic_history
WHERE stage='paper-input' AND observed_at BETWEEN %s AND %s
ORDER BY ABS(observed_at-%s), id LIMIT 1"""


# The indexed last-observation query does not scan private portfolios, trade
# history, quotes, credentials, subscriptions or full diagnostic history.
_LATEST_SQL = """SELECT observed_at, payload FROM bob_diagnostic_history
WHERE stage='paper-input' AND recorded_at >= now() - interval '7 days'
ORDER BY recorded_at DESC LIMIT 1"""


def latest(conn, now_ms=None, session_mode=None):
    """Observe Monday readiness without starting paper trades or market fetches.

    'checked' means the virtual account evaluation returned without an error.
    Neither checked nor ready/fresh establishes an executable product quote.
    No capture during a weekend or before this instrument existed is NOT a
    stopped-worker or missed-trade finding.
    """
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    if _ms(now_ms) is None:
        return {"status":"unavailable", "readOnly":True, "reason":"invalid-clock"}
    if session_mode is None:
        import background_push
        session_mode = background_push.degiro_session(now_ms)
    if session_mode not in ("preparation", "trading", "night", "weekend"):
        return {"status":"unavailable", "readOnly":True, "reason":"unknown-session"}
    try:
        with conn.transaction():
            row = conn.execute(_LATEST_SQL).fetchone()
    except Exception:
        return {"status":"unavailable", "readOnly":True,
                "reason":"paper-input-query-unavailable",
                "sessionMode":session_mode}
    observed_at = float(row[0]) * 1000 if (row and type(row[0]) in (int,float,Decimal)
                   and math.isfinite(float(row[0]))) else None
    payload = row[1] if row and isinstance(row[1],dict) else {}
    age_seconds = (round((now_ms-observed_at)/1000,3)
                   if observed_at is not None and now_ms>=observed_at else None)
    observed_profiles = []
    seen = set()
    for p in (payload.get("profiles") or [])[:len(_ALLOWED_PROFILES)]:
        if not isinstance(p,dict) or p.get("profile") not in _ALLOWED_PROFILES:
            continue
        name = p["profile"]
        if name in seen:
            continue
        seen.add(name)
        data_at = _ms(p.get("dataAt"))
        bar_at = _ms(p.get("barAt"))
        age_at_check = (round((observed_at-data_at)/1000,3)
                        if observed_at is not None and data_at is not None
                        and 0<=observed_at-data_at else None)
        outcome = p.get("outcome") if p.get("outcome") in ("checked","evaluation-error") else "unknown"
        observed_profiles.append({
            "profile":name, "outcome":outcome,
            "ready":p.get("ready") if type(p.get("ready")) is bool else None,
            "priceFresh":p.get("priceFresh") if type(p.get("priceFresh")) is bool else None,
            "originalDataAt":data_at, "originalBarAt":bar_at,
            "sourceAgeAtCaptureSeconds":age_at_check,
        })
    covered = len(observed_profiles)
    checked = sum(p["outcome"]=="checked" for p in observed_profiles)
    ready_fresh = sum(p["outcome"]=="checked" and p["ready"] is True
                      and p["priceFresh"] is True
                      and p["sourceAgeAtCaptureSeconds"] is not None
                      and p["sourceAgeAtCaptureSeconds"] <= 60
                      for p in observed_profiles)
    if session_mode != "trading":
        state = "paused-outside-user-trading-window"
    elif observed_at is None:
        state = "no-post-commit-capture-observed"
    elif age_seconds is None or age_seconds > 180:
        state = "last-capture-not-current"
    elif covered < len(_ALLOWED_PROFILES):
        state = "recent-capture-partial-profile-coverage"
    else:
        state = "recent-all-profile-capture"
    return {
        "status":"observed" if observed_at is not None else "not-yet-observed",
        "readOnly":True, "realOrders":False,
        "sessionMode":session_mode, "state":state,
        "observedAt":observed_at, "ageSeconds":age_seconds,
        "profilesObserved":covered, "profilesChecked":checked,
        "profilesFreshReady":ready_fresh, "profilesExpected":len(_ALLOWED_PROFILES),
        "profiles":observed_profiles,
        "scope":"last-post-commit-paper-input-capture-only",
        "note":"Outside the configured 08:00–22:00 Swiss user trading window a pause is "
               "expected, not proof of exchange closure. Missing or old telemetry "
               "alone cannot establish a worker outage. Successful evaluations "
               "do not prove trade entries, executable issuer quotes, gains or "
               "that an older data gap was repaired.",
    }


def report(conn, accounts, now_ms=None):
    """Bounded indexed SELECTs against original worker input capture clocks."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    if _ms(now_ms) is None:
        return {"status": "unavailable", "readOnly": True, "reason": "invalid-clock"}
    if not isinstance(accounts, list):
        return {"status": "unavailable", "readOnly": True, "reason": "accounts-unavailable"}
    original = _times(accounts)
    times = original[-MAX_EVENTS:]
    if not times:
        return {"status": "unavailable", "readOnly": True, "reason": "no-recorded-gap-clocks"}
    counts = {"workerInputNearby": 0, "noWorkerCaptureNearby": 0,
              "outsideRetention": 0, "queryUnavailable": 0,
              "nearbyProfileInputFresh": 0, "nearbyProfileInputUnfreshOrError": 0}
    items = []
    for at in times:
        item = {"eventAt": at, "state": "unknown", "capturedAt": None,
                "timeRelation": None, "deltaSeconds": None, "profiles": []}
        if at < now_ms - RETENTION_MS or at > now_ms:
            item["state"] = "outside-retention-or-future"
            counts["outsideRetention"] += 1
        else:
            try:
                with conn.transaction():
                    row = conn.execute(_SQL,
                        ((at-WINDOW_MS)/1000, (at+WINDOW_MS)/1000, at/1000)).fetchone()
                if row and type(row[0]) in (int, float, Decimal) and math.isfinite(float(row[0])):
                    at_ms = float(row[0]) * 1000
                    stored = row[1] if isinstance(row[1], dict) else {}
                    observed = []
                    for field in (stored.get("profiles") or [])[:len(_ALLOWED_PROFILES)]:
                        if not isinstance(field, dict) or field.get("profile") not in _ALLOWED_PROFILES:
                            continue
                        observed.append({
                            "profile": field["profile"],
                            "outcome": field.get("outcome") if field.get("outcome") in ("checked", "evaluation-error") else "unknown",
                            "ready": field.get("ready") if type(field.get("ready")) is bool else None,
                            "priceFresh": field.get("priceFresh") if type(field.get("priceFresh")) is bool else None,
                            "dataAt": _ms(field.get("dataAt")),
                            "barAt": _ms(field.get("barAt")),
                        })
                    item.update(state="worker-input-captured-near-gap",
                        capturedAt=at_ms,
                        timeRelation="before-or-at-event" if at_ms <= at else "after-event",
                        deltaSeconds=round(abs(at_ms-at)/1000,3), profiles=observed)
                    counts["workerInputNearby"] += 1
                    if any(p["outcome"] == "checked" and p["ready"] is True and p["priceFresh"] is True
                           and p["dataAt"] is not None for p in observed):
                        counts["nearbyProfileInputFresh"] += 1
                    if any(p["outcome"] != "checked" or p["ready"] is not True or p["priceFresh"] is not True
                           for p in observed):
                        counts["nearbyProfileInputUnfreshOrError"] += 1
                else:
                    item["state"] = "no-worker-input-capture-in-window"
                    counts["noWorkerCaptureNearby"] += 1
            except Exception:
                item["state"] = "input-history-query-unavailable"
                counts["queryUnavailable"] += 1
        items.append(item)
    return {"status": "partial" if counts["queryUnavailable"] or len(times)<len(original) else "observed",
            "readOnly": True, "realOrders": False, "windowSeconds": 90,
            "sampledDistinctClocks": len(times), "totalDistinctClocks": len(original),
            "truncated": len(times)<len(original), "counts": counts, "items": items,
            "scope": "post-deployment-worker-input-capture-not-trade-outcome",
            "note": "A missing capture before instrumentation or across a dropped async event proves nothing. "
                    "Nearby capture documents worker inputs, not an available product bid, settled exit, "
                    "correct strategy result or recovered historical data. No backfill."}
