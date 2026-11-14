"""Read-only five-point storage guardrail, with no quota or reclaim assumptions.

Physical Render usage and logical PostgreSQL growth are separate measurements:
the latter must never be presented as provider volume reclaimed or its growth.
All decisions are observational; no archiving, deletion, rewrite, alert sending,
or paid provisioning is authorized by this module.
"""
import math
from datetime import datetime, timezone

from storage_capacity import ALLOCATION_BYTES

# Early warning thresholds are *physical volume percentages* of the confirmed 5 GB.
# These do not replace the guarded cold-writer pressure policy or grant writes.
LIMITS = ((90, "emergency"), (80, "high"), (70, "action"), (50, "caution"))
FAST_LOGICAL_DAY = 40_000_000
_JOURNAL_APPROVED_CAP = 60_000
_MAX_DAYS = 4


def _nonnegative_int(v, maximum=10**13):
    return type(v) is int and 0 <= v <= maximum


def _verified_time(value):
    if not isinstance(value, str) or not 20 <= len(value) <= 42:
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.timestamp() if date.tzinfo is not None else None
    except (ValueError, OverflowError, TypeError):
        return None


def assess(*, physical_bytes=None, physical_observed_at=None,
           allocation_bytes=ALLOCATION_BYTES, database_bytes=None,
           daily=None, diagnostic_live_estimate=None,
           archive_verified_at=None, now=None, drive_quota_available=None):
    """Classify fixed and bounded telemetry. Never trigger maintenance or messaging."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    valid_now = type(now) in (int, float) and math.isfinite(now) and now >= 0
    fresh = (valid_now and type(physical_observed_at) in (int, float)
             and math.isfinite(physical_observed_at)
             and 0 <= now-physical_observed_at <= 300)
    physical = (_nonnegative_int(physical_bytes)
                and _nonnegative_int(allocation_bytes)
                and allocation_bytes == ALLOCATION_BYTES and fresh)
    percent = round(100 * physical_bytes/allocation_bytes, 1) if physical else None
    level = "unknown" if percent is None else next(
        (name for threshold, name in LIMITS if percent >= threshold), "normal")

    # A daily PostgreSQL-size difference is not a physical-volume growth rate.
    deltas = []
    starts = set()
    for item in (daily[:_MAX_DAYS] if type(daily) is list else []):
        if type(item) is not dict or item.get("status") != "observed":
            continue
        value = item.get("dbDelta")
        slot = item.get("startSlot")
        if (type(value) is int and -10**9 <= value <= 10**9
                and _nonnegative_int(slot, 10**11) and slot not in starts):
            starts.add(slot)
            deltas.append(value)
    rapid_days = sum(v >= FAST_LOGICAL_DAY for v in deltas)
    trend = ("insufficient" if len(deltas) < 2 else
             "rapid-logical-growth" if rapid_days >= 2 else "observed-not-persistent")
    max_daily = max(deltas) if deltas else None

    live = diagnostic_live_estimate if _nonnegative_int(diagnostic_live_estimate) else None
    cap = (None if live is None else
           "estimated-over-approved-cap" if live > _JOURNAL_APPROVED_CAP else
           "estimated-within-approved-cap")

    archive_at = _verified_time(archive_verified_at)
    age = (now - archive_at if valid_now and archive_at is not None else None)
    proof = ("not-observed" if age is None or age < 0 else
             "fresh" if age <= 6 * 3600 else "stale")

    # The quota number is the *last verified archive preflight snapshot*, not
    # the current Google account quota and not upload permission.
    drive = (drive_quota_available if _nonnegative_int(drive_quota_available)
             else None)

    return {
        "status": "observed" if physical else "physical-measurement-unavailable",
        "physicalUsedPct": percent,
        "severity": level,
        "logicalDailySampleCount": len(deltas),
        "maxObservedLogicalDailyIncreaseBytes": max_daily,
        "logicalGrowthState": trend,
        "diagnosticJournalRowsEstimated": live,
        "diagnosticJournalCapState": cap,
        "lastVerifiedArchiveProofState": proof,
        "lastArchiveQuotaAvailableBytes": drive,
        "archiveQuotaIsCurrent": False,
        "readOnly": True, "ordersAffected": False,
        "automaticArchiveTriggered": False,
        "retentionChanged": False,
        "deletionAuthorized": False,
        "diskBytesFreed": None,
        "scope": "fresh-physical-volume-and-bounded-logical-growth-are-distinct",
    }
