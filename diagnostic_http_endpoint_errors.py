"""Privacy-safe classification of bounded HTTP *request-log samples*.

Goal 15: offline read-only diagnosis, never an assertion of live Render
coverage. Only allowlisted static routes are named. Authentication denial
is not server downtime and 5xx alone cannot establish a crash cause.
"""
from collections import Counter
from datetime import datetime, timezone

MAX_LOGS = 250
SERVICES = frozenset(("bob-private-scanner", "bob-push-service"))
ROUTES = frozenset((
    "/health", "/health/background", "/diagnostics", "/diagnostic-history",
    "/api/live", "/api/mtf", "/api/collection-status", "/api/market-cards",
    "/api/self-healing", "/api/problems", "/api/repair-statistics",
    "/api/push/subscribe", "/api/push/unsubscribe", "/api/push/preferences",
))


def _timestamp(value):
    if not isinstance(value, str) or not 10 <= len(value) <= 42:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def _code(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        code = value
    elif isinstance(value, str) and len(value) == 3 and value.isascii() and value.isdecimal():
        code = int(value)
    else:
        return None
    return code if 100 <= code <= 599 else None


def _route(value):
    # Never include arbitrary paths, personal identifiers, query strings.
    if not isinstance(value, str) or len(value) > 2048:
        return "other-unclassified"
    path = value.split("?", 1)[0].split("#", 1)[0]
    return path if path in ROUTES else "other-unclassified"



def _request(row):
    """Take only fixed, sanitized fields from structured or Bob app logs."""
    if not isinstance(row, dict):
        return None
    if row.get("type", "request") == "request" and "statusCode" in row:
        return row.get("path"), row.get("statusCode")
    message = row.get("message")
    if not isinstance(message, str) or len(message) > 512:
        return None
    parts = message.split()
    if not parts or parts[0] not in ("BOB_HTTP", "BOB_PUSH_HTTP"):
        return None
    fields = {}
    for part in parts[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            if key in ("path", "status", "method"):
                fields[key] = value
    if fields.get("method") not in ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"):
        return None
    return fields.get("path"), fields.get("status")

def classify(logs, *, service, window_start, window_end, has_more=False):
    """Classify bounded, caller-supplied logs; original source not verified.

    Input: timestamped request records OR Bob app-log lines with fixed prefixes
    BOB_HTTP/BOB_PUSH_HTTP. Unknown log messages cannot be classified.
    Incomplete/paginated captures cannot prove the absence of HTTP errors.
    """
    start, end = _timestamp(window_start), _timestamp(window_end)
    if (service not in SERVICES or not isinstance(logs, list)
            or not start or not end or start >= end
            or type(has_more) is not bool):
        return {"status": "insufficient-evidence", "readOnly": True,
                "realOrders": False, "liveVerified": False}
    counts = Counter()
    by_route = {}
    considered = min(len(logs), MAX_LOGS)
    invalid = 0
    for row in logs[:MAX_LOGS]:
        request = _request(row)
        if request is None:
            invalid += 1
            continue
        stamp = _timestamp(row.get("timestamp"))
        path, raw_code = request
        code = _code(raw_code)
        if stamp is None or code is None or not start <= stamp <= end:
            invalid += 1
            continue
        band = f"{code // 100}xx"
        route = _route(path)
        counts[band] += 1
        bucket = by_route.setdefault(route, Counter())
        bucket[band] += 1
        if code in (401, 403):
            bucket["accessDenied"] += 1
        if code >= 500:
            bucket["serverErrors"] += 1
    bands = ("1xx", "2xx", "3xx", "4xx", "5xx")
    totals = {band: counts[band] for band in bands}
    return {
        "status": "classified-sample" if sum(totals.values()) else "insufficient-evidence",
        "service": service, "windowStart": start.isoformat(),
        "windowEnd": end.isoformat(), "readOnly": True, "realOrders": False,
        "liveVerified": False, "completeTrafficProven": False,
        "source": "caller-supplied-request-log-sample-not-provider-verified",
        "sampledRecords": considered, "validRequestRecords": sum(totals.values()),
        "invalidOrIgnoredRecords": invalid,
        "sampleTruncated": len(logs) > MAX_LOGS or has_more,
        "httpClasses": totals,
        "endpoints": [{
            "endpoint": route,
            "httpClasses": {band: entries[band] for band in bands},
            "accessDenied": entries["accessDenied"],
            "serverErrors": entries["serverErrors"]
        } for route, entries in sorted(by_route.items())],
        "note": "4xx alone is not an outage, 5xx alone is not a crash cause; "
                "missing or paginated logs never prove zero errors.",
    }
