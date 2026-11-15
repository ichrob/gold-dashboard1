"""Fixed read-only Gemini diagnostic views and conservative simulation triage.

Works ONLY on Bob's existing sanitized diagnostic snapshot. No new source reads,
model calls, file access, writes, paper orders or live broker actions.
"""
import json

VIEWS = {
    "simulation-accounts": ("simulationAndPush", "accounts"),
    "simulation-history": ("simulationAndPush", "history"),
    "simulation-details": ("simulationAndPush", "details"),
    "comparison-evidence": ("comparisonEvidence",),
    "comparison-health": ("comparisonHealth",),
    "study-quality": ("newStudiesBrief",),
    "paper-profit": ("paperProfitEvidence",),
    "simulation-runtime": ("simulationRuntimeBrief",),
}
MAX_PAGE = 20
MAX_ITEMS = 5
MAX_BYTES = 64000


def _bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8"))


def validate_view(arguments):
    if not isinstance(arguments, dict) or set(arguments) - {"view", "page", "pageSize"}:
        raise ValueError("invalid-view-arguments")
    view = arguments.get("view")
    page = arguments.get("page", 0)
    count = arguments.get("pageSize", 3)
    if (type(view) is not str or view not in VIEWS or type(page) is not int
            or not 0 <= page <= MAX_PAGE or type(count) is not int
            or not 1 <= count <= MAX_ITEMS):
        raise ValueError("invalid-view-arguments")
    return view, page, count


def _window(value, *, page, count, depth=0):
    """Paginate existing lists, including nested lists; never invent observations."""
    if depth >= 12:
        return {"status": "partial", "reason": "view-depth-limit"}
    if isinstance(value, list):
        offset = page * count
        return {"totalItems": len(value), "offset": offset, "pageSize": count,
                "hasMore": offset + count < len(value),
                "items": [_window(item, page=0, count=count, depth=depth + 1)
                          for item in value[offset:offset + count]]}
    if isinstance(value, dict):
        return {key: _window(item, page=page, count=count, depth=depth + 1)
                for key, item in value.items()}
    return value


def project_view(report, arguments, *, max_bytes=MAX_BYTES):
    """Expose one fixed subtree of the existing sanitized report per request."""
    view, page, count = validate_view(arguments)
    if type(max_bytes) is not int or not 1024 <= max_bytes <= MAX_BYTES:
        raise ValueError("invalid-view-budget")
    root = report if isinstance(report, dict) else {}
    value = root.get("areas")
    for key in VIEWS[view]:
        value = value.get(key) if isinstance(value, dict) else None
    source_present = value is not None
    if not source_present:
        value = {"status": "unavailable", "reason": "source-area-not-observed"}
    result = {"readOnly": True, "realOrders": False,
              "scope": "existing-sanitized-snapshot-no-new-source-queries",
              "view": view, "page": page, "pageSize": count,
              "observedAt": root.get("observedAt"),
              "sourceStatus": value.get("status", "unknown")
                              if isinstance(value, dict) else "unknown",
              "status": "observed" if source_present else "unavailable",
              "data": _window(value, page=page, count=count)}
    # Narrow a response by reducing its fixed per-list window. When even the
    # smallest window cannot fit, report explicit omission rather than silently
    # dropping proof or fabricating a complete study.
    while _bytes(result) > max_bytes and count > 1:
        count -= 1
        result["pageSize"] = count
        result["data"] = _window(value, page=page, count=count)
        result["status"] = "partial"
        result["reason"] = "view-window-reduced-to-fit"
    if _bytes(result) > max_bytes:
        result["data"] = {"status": "unavailable",
                          "reason": "omitted-response-size-limit"}
        result["status"] = "partial"
        result["reason"] = "view-exceeds-response-budget"
    elif source_present and isinstance(value, dict) and value.get("status") in (
            "partial", "unavailable", "stale", "failed", "degraded"):
        result["status"] = "partial"
    return result


def simulation_audit(report):
    """Conservative independent triage; no win rates, invented fills or trades."""
    root = report if isinstance(report, dict) else {}
    areas = root.get("areas") if isinstance(root.get("areas"), dict) else {}
    study = areas.get("newStudiesBrief") or {}
    runtime = areas.get("simulationRuntimeBrief") or {}
    paper = areas.get("paperProfitEvidence") or {}
    comparison = areas.get("comparisonHealth") or {}
    omitted = root.get("omittedAreas") or []
    quality = study.get("quality") if isinstance(study, dict) else {}
    source = quality if isinstance(quality, dict) else {}
    original = source.get("studies") if isinstance(source.get("studies"), list) else []
    results = []
    for row in original[:12]:
        if not isinstance(row, dict):
            continue
        results.append({k: row.get(k) for k in (
            "id", "started", "complete", "inconclusive", "open",
            "invalid", "workerErrors", "recentOriginalBlockCode")})
    states = {key: (value.get("status", "unavailable")
                    if isinstance(value, dict) else "unavailable")
              for key, value in (("newStudiesBrief", study),
                                 ("simulationRuntimeBrief", runtime),
                                 ("paperProfitEvidence", paper),
                                 ("comparisonHealth", comparison))}
    complete = (
        all(s == "observed" for s in states.values())
        and not root.get("truncated")
        and not omitted
        and source.get("status") == "observed"
        and study.get("fullOriginalHistoryVerified") is True
        and paper.get("fullHistoryRead") is True
        and paper.get("netProductReturnsVerified") is True
    )
    return {"readOnly": True, "realOrders": False,
            "observedAt": root.get("observedAt"),
            "status": "observed" if complete else "partial",
            "scope": "bounded-original-evidence-not-causal-or-profit-validation",
            "areaStatus": states, "studies": results,
            "omittedAreas": [k for k in omitted if k in (
                "simulationAndPush", "comparisonEvidence")],
            "originalCoverageComplete": bool(complete),
            "netProductReturnsVerified": bool(paper.get("netProductReturnsVerified") is True),
            "strategyWinnerConfirmed": bool(study.get("strategyWinnerConfirmed") is True),
            "note": "Inconclusive paper cases are not realised losses; absent original "
                    "quotes or exits cannot be interpolated. This tool makes no repairs."}
