"""Offline, fail-closed capacity admission for a *manual* Aiven synthetic probe.

No network access, database writes, background tasks or credentials. Its
"candidate" result is never permission to migrate or run live research.
"""
from datetime import datetime, timezone

from aiven_host_capacity_review import review

MAX_SYNTHETIC_BUDGET_BYTES = 16 * 1024 * 1024
RAM_MAX_PCT = 70.0
DISK_MAX_PCT = 55.0
SQL_MAX_AGE_SECONDS = 300
RECOVERY_MAX_AGE_SECONDS = 6 * 3600


def _instant(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            return None
        return result.astimezone(timezone.utc)
    except ValueError:
        return None


def _fresh(value, now, limit):
    stamp = _instant(value)
    return stamp is not None and 0 <= (now - stamp).total_seconds() <= limit


def assess(host_sample, sql_sample, archive_proof, *, requested_bytes, now=None):
    """Report whether a small manual synthetic test merits an operator review.

    The host sample is supplied by the operator. It is not authenticated by
    this pure evaluator. A candidate decision MUST NOT trigger automatic SQL.
    """
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("now requires an explicit timezone")
    now = now.astimezone(timezone.utc)
    reasons = []
    if type(requested_bytes) is not int or not 0 < requested_bytes <= MAX_SYNTHETIC_BUDGET_BYTES:
        reasons.append("synthetic-budget-invalid")

    if not isinstance(host_sample, dict) or any(
        not isinstance(host_sample.get(key), str) or not host_sample[key].strip()
        for key in ("project", "service", "node")
    ):
        reasons.append("aiven-host-identity-missing")

    report = review(host_sample, sql_sample, now=now)
    ram_pct, disk_pct = report.get("ramUsedPct"), report.get("diskUsedPct")
    if report["hostMemoryStatus"] != "observed" or ram_pct is None:
        reasons.append("aiven-host-ram-unverified")
    elif ram_pct > RAM_MAX_PCT:
        reasons.append("aiven-host-ram-reserve-insufficient")
    if disk_pct is None:
        reasons.append("aiven-host-disk-unverified")
    elif disk_pct > DISK_MAX_PCT:
        reasons.append("aiven-host-disk-reserve-insufficient")

    if not isinstance(sql_sample, dict) or sql_sample.get("status") != "observed" or not (
        report.get("sqlCorrelated") and _fresh(sql_sample.get("observedAt"), now, SQL_MAX_AGE_SECONDS)
    ):
        reasons.append("aiven-sql-freshness-unverified")
    else:
        values = [sql_sample.get(key) for key in (
            "maxConnections", "clientConnections", "idleTransactions", "longActiveClients",
            "databaseBytes",
        )]
        if not all(type(v) is int and v >= 0 for v in values):
            reasons.append("aiven-sql-counters-unverified")
        else:
            capacity, clients, idle, long_queries, db_size = values
            if capacity < 1 or clients > min(3, capacity // 4):
                reasons.append("aiven-connections-reserve-insufficient")
            if idle or long_queries:
                reasons.append("aiven-query-contention")
            # SQL logical database size is an additional warning, never
            # substituted for real provider disk-occupancy metrics.
            if db_size == 0:
                reasons.append("aiven-database-size-unverified")

    expected = ("restoreVerified", "remoteDownloadVerified", "encryptionVerified",
                "recoveryKeyVerified", "restoreIsolationVerified")
    if (not isinstance(archive_proof, dict)
            or archive_proof.get("latestVerifiedState") != "verified"
            or not all(archive_proof.get(key) is True for key in expected)
            or not _fresh(archive_proof.get("verifiedAt"), now, RECOVERY_MAX_AGE_SECONDS)):
        reasons.append("independent-recovery-proof-unverified")

    if report["findings"]:
        reasons.append("aiven-host-or-sql-findings-present")
    return {
        "status": ("candidate-for-manual-synthetic-test-only" if not reasons else "blocked"),
        "manualReviewOnly": True,
        "automaticDatabaseWritesAllowed": False,
        "productionMigrationAllowed": False,
        "newSpendAllowed": False,
        "requestedBytes": requested_bytes if type(requested_bytes) is int else None,
        "reasons": list(dict.fromkeys(reasons)),
    }
