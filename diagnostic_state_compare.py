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
    bad = frozenset(code for code in bad[:20] if isinstance(code, str) and code in _CODES) \
          if isinstance(bad, list) else frozenset()
    return {"at": at, "build": build, "status": status, "bad": bad}


def _pair(before, after, scope):
    if before is None or after is None:
        return {"status": "insufficient-evidence", "scope": scope,
                "isRepairVerified": False, "isDeploymentRegressionVerified": False}
    added = sorted(after["bad"] - before["bad"])
    cleared = sorted(before["bad"] - after["bad"])
    # Change of a sampled technical status is a lead, never a root cause.
    possible_regression = bool(added) or (
        before["status"] in ("ok", "observed", "healthy") and
        after["status"] in ("degraded", "failed", "unavailable", "stale"))
    return {
        "status": "observed-comparison",
        "scope": scope,
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
        "note": "Only sampled technical health history; no causal deployment, "
                "gold market, broker, device or trade-outcome verification.",
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
        "limitations": "No observation before instrumentation is no proof of "
                       "health. No comparison is a verified repair, deployment "
                       "regression or confirmation of end-to-end features.",
    }
