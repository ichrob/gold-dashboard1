"""Free-only, privacy-preserving summary of connected Cloudflare diagnostics.

This module does NOT fetch anything or open GitHub issues. The existing Bob
Fehlerzentrale can apply it to *authorized, read-only* Cloudflare API responses.
Only fixed worker names and numeric aggregates may leave this boundary.
Unknown coverage must never be reported as healthy.
"""
from __future__ import annotations

from math import isfinite

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
        if isinstance(worker, str) and worker in results:
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



# These are existing Cloudflare cron schedules, NOT expected success receipts.
# Three intervals give free Workers time for normal Cron delivery jitter.
CRON_CADENCE_SECONDS = {
    "bob-watchdog-clock": 10 * 60,
    "bob-oracle-a1-retry": 30 * 60,
}


def summarize_cron_receipts(response, *, now_epoch_seconds):
    """Read *observed scheduled events*, not successful repairs or OCI Applies.

    Cloudflare /telemetry/query calculation must be the saved, read-only
    max($workers.event.scheduledTime) grouped by $metadata.service.
    Numeric scheduledTime values are Unix seconds (possibly fractional).
    No log text, errors, headers, account data or arbitrary worker names leave
    this boundary. Missing observations are UNKNOWN, never an outage claim.
    """
    empty = {
        "state": "unknown",
        "workers": {
            name: {"state": "unknown", "lastScheduledAt": None, "ageSeconds": None}
            for name in CRON_CADENCE_SECONDS
        },
        "allRecentlyObserved": None,
    }
    if (type(now_epoch_seconds) not in (int, float)
            or not isfinite(now_epoch_seconds) or now_epoch_seconds <= 0
            or not isinstance(response, dict) or response.get("success") is not True):
        return empty
    data = response.get("result")
    calculations = data.get("calculations") if isinstance(data, dict) else None
    if not isinstance(calculations, list) or len(calculations) > 10:
        return empty
    matches = [item for item in calculations if isinstance(item, dict)
               and item.get("alias") == "lastScheduledEpochSeconds"]
    if len(matches) != 1:
        return empty
    aggregates = matches[0].get("aggregates")
    if not isinstance(aggregates, list) or len(aggregates) > 50:
        return empty
    latest = {}
    for row in aggregates:
        if not isinstance(row, dict):
            return empty
        worker = row.get("groupKey")
        if type(worker) is not str or worker not in CRON_CADENCE_SECONDS:
            continue
        value = row.get("value")
        if (type(value) not in (float, int) or not isfinite(value)
                or value <= 0 or value > now_epoch_seconds + 120):
            return empty
        latest[worker] = max(latest.get(worker, 0), value)
    workers = {}
    for name, cadence in CRON_CADENCE_SECONDS.items():
        observed = latest.get(name)
        if observed is None:
            workers[name] = {"state": "not-observed", "lastScheduledAt": None,
                             "ageSeconds": None}
        else:
            age = max(0, int(now_epoch_seconds - observed))
            workers[name] = {"state": "recent" if age <= 3 * cadence else "old-observation",
                             "lastScheduledAt": int(observed), "ageSeconds": age}
    return {"state": "observed", "workers": workers,
            "allRecentlyObserved": all(v["state"] == "recent" for v in workers.values())}


def central_digest(usage, issues, settings, *, cron=None, now_epoch_seconds=None):
    """Fixed-schema internal handoff, never a recovery or a push notification."""
    u = summarize_usage(usage)
    i = summarize_issues(issues)
    s = summarize_settings(settings)
    receipts = summarize_cron_receipts(cron, now_epoch_seconds=now_epoch_seconds)
    return {
        "version": 1, "source": "cloudflare-observability-readonly",
        "usage": u, "issues": i, "coverage": s, "cronReceipts": receipts,
        "allWorkersObservable": all(
            v["logs"] == "enabled" and v["issues"] == "enabled"
            for v in s.values()
        ),
        "healthy": None,  # Missing incidents is NEVER proof of health.
        "costAuthorized": False, "newPushChannel": False,
    }
