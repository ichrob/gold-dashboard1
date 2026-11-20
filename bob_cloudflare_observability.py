"""Free-only, privacy-preserving summary of connected Cloudflare diagnostics.

This module does NOT fetch anything or open GitHub issues. The existing Bob
Fehlerzentrale can apply it to *authorized, read-only* Cloudflare API responses.
Only fixed worker names and numeric aggregates may leave this boundary.
Unknown coverage must never be reported as healthy.
"""
from __future__ import annotations

WORKERS = (
    "bob-watchdog-clock",
    "proud-gold-scanner-background-416f",
    "bob-oracle-a1-retry",
    "bob-free-ai-review",
)
FREE_INGESTION_LIMIT_BYTES = 500_000_000  # Cloudflare Free from 2026-12-01
WARNING_BYTES = 400_000_000  # Advisory only; not a billable-service switch.


def _nonnegative_int(value):
    return type(value) is int and value >= 0


def summarize_usage(response):
    """Summarize a bounded Cloudflare Observability /usage response.

    The caller must query a specifically stated time interval. These bytes
    are *observed ingestion*, NOT a complete invoice or daily usage forecast.
    """
    blank = {"state": "unknown", "events": None, "bytes": None,
             "workers": {}, "otherEvents": None, "warnings": []}
    if not isinstance(response, dict) or response.get("success") is not True:
        return blank
    data = response.get("result")
    if not isinstance(data, dict) or not isinstance(data.get("breakdown"), list):
        return blank
    rows = data["breakdown"]
    if len(rows) > 1000 or not _nonnegative_int(data.get("events")):
        return blank
    results = {worker: {"events": 0, "bytes": 0} for worker in WORKERS}
    events, size, other = 0, 0, 0
    for row in rows:
        if (not isinstance(row, dict) or not _nonnegative_int(row.get("count"))
                or not _nonnegative_int(row.get("eventSize"))):
            return blank
        events += row["count"]
        size += row["eventSize"]
        worker = row.get("service")
        if worker in results:
            results[worker]["events"] += row["count"]
            results[worker]["bytes"] += row["eventSize"]
        else:
            # Never copy uncontrolled service names from third-party responses.
            other += row["count"]
    # The breakdown may be partial. Refuse a fabricated complete account total.
    if events != data["events"]:
        return {**blank, "warnings": ["partial_usage_breakdown"]}
    warnings = []
    if size >= WARNING_BYTES:
        warnings.append("high_observed_ingestion_check_free_plan")
    return {"state": "observed", "events": events, "bytes": size,
            "workers": results, "otherEvents": other, "warnings": warnings}


def summarize_issues(response):
    """Read numeric issues summary, not titles, descriptions or stack traces."""
    unknown = {"state": "unknown", "active": None, "occurrences": None}
    if not isinstance(response, dict) or response.get("success") is not True:
        return unknown
    result = response.get("result")
    if not isinstance(result, dict):
        return unknown
    active, occurrences = result.get("activeIssues"), result.get("activeOccurrences")
    if not _nonnegative_int(active) or not _nonnegative_int(occurrences):
        return unknown
    return {"state": "observed", "active": active, "occurrences": occurrences}


def summarize_settings(responses):
    """Coverage status only. No worker secrets, variables or bindings are read."""
    out = {}
    for worker in WORKERS:
        envelope = responses.get(worker) if isinstance(responses, dict) else None
        data = envelope.get("result") if isinstance(envelope, dict) and envelope.get("success") is True else None
        obs = data.get("observability") if isinstance(data, dict) else None
        logs = obs.get("logs") if isinstance(obs, dict) else None
        issues = obs.get("issues") if isinstance(obs, dict) else None
        out[worker] = {
            "logs": "enabled" if isinstance(logs, dict) and obs.get("enabled") is True and logs.get("enabled") is True
                     else "disabled" if isinstance(logs, dict) and logs.get("enabled") is False
                     else "unknown",
            "issues": "enabled" if isinstance(issues, dict) and issues.get("enabled") is True
                       else "disabled" if isinstance(issues, dict) and issues.get("enabled") is False
                       else "unknown",
        }
    return out


def central_digest(usage, issues, settings):
    """Fixed-schema internal handoff, never a recovery or a push notification."""
    u = summarize_usage(usage)
    i = summarize_issues(issues)
    s = summarize_settings(settings)
    return {
        "version": 1, "source": "cloudflare-observability-readonly",
        "usage": u, "issues": i, "coverage": s,
        "allWorkersObservable": all(
            v["logs"] == "enabled" and v["issues"] == "enabled"
            for v in s.values()
        ),
        "healthy": None,  # Missing incidents is NEVER proof of health.
        "costAuthorized": False, "newPushChannel": False,
    }
