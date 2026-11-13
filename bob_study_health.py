"""Bounded, public-safe status of prospective ORIGINAL Bob study failures.

One indexed control-row read is performed by the existing push health endpoint.
Never publish source prices, ISINs, private diagnostics, raw provider errors or
historical aggregate counters. No change to trading, models or stored cases.
"""
import math
import time
from datetime import datetime
from zoneinfo import ZoneInfo

SCOPE = "bob-original-study-watchdog-v1"
INPUT_CODE = "study-original-input-degraded"
OUTCOME_CODE = "study-outcome-coverage-degraded"
WORKER_CODE = "study-worker-stale"
CODES = frozenset((INPUT_CODE, OUTCOME_CODE, WORKER_CODE))
WINDOW_MS = 20*60000
OUTCOME_WINDOW_MS = 4*3600000


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def snapshot(control, now_ms=None, *, trading=False):
    """Only *new* original checks/outcomes may generate an alert.

    Historical cumulative totals and automatically estimated cases never do.
    Intentional night/weekend pauses are not faults. During business hours,
    classify stale/missing control separately from a confirmed healthy study.
    """
    result = dict(scope=SCOPE, status="unavailable", codes=[],
                  readOnly=True, realOrders=False)
    if not trading:
        result["status"] = "paused"
        return result
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    if not _number(now_ms) or now_ms <= 0 or not isinstance(control,dict):
        return result
    if control.get("status") not in ("collecting", "draining"):
        result["status"] = "inactive" if control.get("status") in (
            "completed-review-required","completed") else "unavailable"
        return result
    checked = control.get("checkedAt")
    if not _number(checked) or checked <= 0 or checked > now_ms+2000:
        return result
    elapsed = now_ms - checked
    if elapsed > 180000:
        if control["status"] == "collecting":
            result.update(status="stale", codes=[WORKER_CODE])
        return result
    q = control.get("quality")
    if not isinstance(q,dict):
        return result
    result["status"] = "observed"
    # Only trusted process-owned small samples in the preceding 20 minutes.
    raw = q.get("recentOriginalChecks")
    checks = []
    if isinstance(raw,list) and len(raw) <= 64:
        checks = [x for x in raw if isinstance(x,dict)
                  and type(x.get("at")) is int
                  and 0 <= now_ms-x["at"] <= WINDOW_MS
                  and type(x.get("valid")) is bool]
    bad = [x for x in checks if not x["valid"]]
    if (len(checks)>=12 and len(bad)>=6 and len(bad)*4>=len(checks)
            and sum(x["at"] >= now_ms-300000 for x in bad)>=2):
        result["codes"].append(INPUT_CODE)
    # Inconclusive coverage is a prospective outcome-quality incident only
    # after enough NEW policy cases and a RECENT failed terminal observation.
    raw = q.get("recentOriginalOutcomes")
    outcomes=[]
    if isinstance(raw,list) and len(raw)<=64:
        outcomes=[x for x in raw if isinstance(x,dict)
                  and type(x.get("at")) is int
                  and 0 <= now_ms-x["at"] <= OUTCOME_WINDOW_MS
                  and x.get("study") in ("warning-confirmed","entry-delay","sideways-filter")
                  and type(x.get("complete")) is bool]
    invalid=[x for x in outcomes if not x["complete"]]
    if (len(outcomes)>=5 and len(invalid)>=4 and len(invalid)*5>=len(outcomes)*3
            and any(x["at"]>=now_ms-45*60000 for x in invalid)):
        result["codes"].append(OUTCOME_CODE)
    return result
