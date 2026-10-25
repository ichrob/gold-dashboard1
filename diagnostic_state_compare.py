"""Compare bounded, already-sanitized health snapshots without claiming repair.

This module is deterministic and read-only. It does not fetch extra history,
load private account records or infer that a deployment caused a change.
"""
import math
import re

_HEALTH = frozenset(("ok", "observed", "healthy", "degraded", "failed",
                     "unavailable", "partial", "stale", "paused"))
# Only Bob's predetermined technical codes; never echo arbitrary payload text.
_CODES = frozenset((
    "repair-watch-stalled", "cfd-worker-stopped", "spot-change-worker-stopped",
    "comparison-worker-stopped", "market-feed-not-current",
    "background-not-current", "market-worker-stopped",
    "background-worker-stopped", "research-worker-stopped",
    "unknown-service-failure",
))
_BUILD = re.compile(r"[a-f0-9]{40}\Z")
MAX_HEALTH_EVENTS = 20


def _sample(event):
    if not isinstance(event, dict) or event.get("stage") != "health":
        return None
    at = event.get("observedAt")
    if type(at) not in (int, float) or not math.isfinite(at) or at <= 0:
        return None
    build = event.get("build")
    if not isinstance(build, str) or not _BUILD.fullmatch(build):
        build = None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    value = payload.get("status")
    status = value if isinstance(value, str) and value in _HEALTH else "unknown"
    bad = payload.get("badCodes")
    # Missing, truncated or malformed evidence is NOT the same as a measured
    # empty error list. Never manufacture a cleared-code conclusion.
    complete_codes = (isinstance(bad, list) and len(bad) <= 20 and
                      all(isinstance(code, str) and code in _CODES for code in bad))
    bad = frozenset(bad) if complete_codes else frozenset()
    session = payload.get("session")
    if not isinstance(session, str) or session not in (
            "trading", "preparation", "night", "weekend"):
        session = None
    return {"at": at, "build": build, "status": status, "bad": bad,
            "codesRecorded": complete_codes, "session": session}


def _pair(before, after, scope):
    if before is None or after is None:
        return {"status": "insufficient-evidence", "scope": scope,
                "isRepairVerified": False, "isDeploymentRegressionVerified": False}
    # Mixing a trading capture with a weekend/night capture is not a valid
    # "after deployment regression" comparison. The timestamps order capture
    # arrival only, NEVER actual Render deployment or service health causality.
    same_session = (before["session"] is not None
                    and before["session"] == after["session"])
    code_delta_known = (same_session and before["codesRecorded"]
                        and after["codesRecorded"])
    added = sorted(after["bad"] - before["bad"]) if code_delta_known else []
    cleared = sorted(before["bad"] - after["bad"]) if code_delta_known else []
    worsened_health = (same_session
                       and before["status"] in ("ok", "observed", "healthy")
                       and after["status"] in ("degraded", "failed", "unavailable", "stale"))
    possible_regression = bool(added) or worsened_health
    comparable_health = (same_session and before["status"] != "unknown"
                         and after["status"] != "unknown")
    assessment = ("possible-in-observed-sample" if possible_regression else
                  "no-regression-in-observed-sample" if comparable_health and code_delta_known
                  else "insufficient-evidence")
    return {
        "status": "observed-comparison",
        "scope": scope,
        "previousSession": before["session"],
        "currentSession": after["session"],
        "sessionComparable": same_session,
        "codeDeltaStatus": "observed" if code_delta_known else "insufficient-evidence",
        "regressionAssessment": assessment,
        "observationsAreDeploymentOrder": False,
        "previousAt": before["at"],
        "currentAt": after["at"],
        "previousBuild": before["build"],
        "currentBuild": after["build"],
        "previousHealth": before["status"],
        "currentHealth": after["status"],
        "newTechnicalCodes": added,
        "clearedTechnicalCodes": cleared,
        "possibleRegression": possible_regression,
        "isRepairVerified": False,
        "isDeploymentRegressionVerified": False,
        "note": "Chronological captures are not a proven deploy sequence. "
                "Absent/malformed code lists and cross-session changes are "
                "insufficient evidence, not cleared errors or repairs. "
                "No causal deployment, broker, device or trade verification.",
    }


def compare(events):
    """Most recent distinct health instants; additionally compare across builds.

    The caller already reads at most 20 events per diagnostic stage from the
    existing seven-day journal. No new SQL or external service access.
    """
    if not isinstance(events, list):
        events = []
    health = sorted((v for event in events[:120]
                     if (v := _sample(event)) is not None),
                    key=lambda v: v["at"], reverse=True)
    newest = health[0] if health else None
    earlier = next((p for p in health[1:] if p["at"] < newest["at"]), None) if newest else None
    before_build = next((p for p in health[1:] if p["at"] < newest["at"]
                         and p["build"] is not None and newest["build"] is not None
                         and p["build"] != newest["build"]), None) if newest else None
    return {
        "readOnly": True,
        "sampledHealthEvents": min(len(health), MAX_HEALTH_EVENTS),
        "stateComparison": _pair(earlier, newest, "two-distinct-health-observations"),
        "deploymentComparison": _pair(before_build, newest,
                                     "different-builds-within-sampled-health-history"),
        "limitations": "Only recent sampled health captures. Different sessions, "
                       "missing code lists and overlapping builds are not comparable "
                       "proof. No repair, deployment-caused regression or end-to-end "
                       "feature is independently verified.",
    }
