"""Tiny, redacted storage view surviving the private MCP response size cap.

Uses only the already collected, sanitized storage report: no SQL, Render
requests, Drive downloads, archive scans, migrations, or trading actions.
Never mistake a logical byte reduction for physically reclaimed provider space.
"""
import math

_STORAGE_STATES = frozenset(("observed", "unavailable", "not-observed",
                            "partial", "stale"))
_BUDGET_STATES = frozenset(("below-budget-threshold", "caution",
                            "action-required"))
_VOLUME_STATES = frozenset(("observed", "unavailable", "no-fresh-observation",
                            "configuration-required", "invalid-response"))
_PROOF_STATES = frozenset(("verified-fresh", "verified-but-stale",
                           "no-verified-restore", "timestamp-unavailable",
                           "recovery-or-archive-proof-missing",
                           "not-observed"))
_PILOT_STATES = frozenset(("disabled", "no-attempt", "not-observed",
                           "running", "failed", "verified-offload",
                           "no-change", "already-claimed", "not-observed",
                           "backup-proof-not-fresh",
                           "fresh-volume-proof-unavailable",
                           "deferred-page-scanned", "deferred-no-eligible-rows",
                           "deferred-sweep-completed", "deferred-busy"))
_ENCRYPTION = "aes-256-gcm-stream-v1"


def _choice(item, allowed, default="unavailable"):
    return item if type(item) is str and item in allowed else default


def _number(item, *, integer=False, maximum=10**13):
    if type(item) is bool or type(item) not in (int, float):
        return None
    if not math.isfinite(item) or not 0 <= item <= maximum:
        return None
    if integer and type(item) is not int:
        return None
    return item


def _clock(item):
    # Never report arbitrary strings from original database receipts.
    if not isinstance(item, str) or not 20 <= len(item) <= 42:
        return None
    from datetime import datetime, timezone
    try:
        value = datetime.fromisoformat(item.replace("Z", "+00:00"))
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else None
    except (ValueError, OverflowError):
        return None


def project(storage):
    """Return only fixed safe fields; no raw receipt, IDs, prices or secrets."""
    missing = {"status": "not-observed", "readOnly": True,
               "physicalBytesFreed": None, "originalRowsChangedByThisView": False,
               "decisionProductPilotAuthorized": False,
               "scope": "read-only-sampled-status-not-physical-reclaim-proof"}
    if not isinstance(storage, dict):
        return missing
    result = dict(missing)
    result["status"] = _choice(storage.get("status"), _STORAGE_STATES,
                               "not-observed")
    result["databaseBytes"] = _number(storage.get("databaseBytes"), integer=True)
    result["configuredAllocationBytes"] = _number(
        storage.get("configuredAllocationBytes"), integer=True)
    result["budgetState"] = _choice(storage.get("budgetState"), _BUDGET_STATES,
                                    "not-observed")
    result["lastSampleAt"] = _number(storage.get("lastSampleAt"), integer=True)

    provider = storage.get("renderVolume")
    provider = provider if isinstance(provider, dict) else {}
    kind = _choice(provider.get("status"), _VOLUME_STATES)
    size = _number(provider.get("diskUsage"), maximum=10**12)
    observed = _number(provider.get("observedAt"), maximum=10**11)
    valid = (kind == "observed" and provider.get("unit") == "bytes"
             and size is not None and observed is not None)
    result["renderVolume"] = {
        "status": "observed" if valid else
                  ("invalid-or-unverified-units" if kind == "observed" else kind),
        "usedBytes": size if valid else None,
        "observedAt": observed if valid else None,
        "unit": "bytes" if valid else None,
        "scope": "physical-provider-volume-single-observation-not-savings"
    }

    worker = storage.get("archiveWorker")
    worker = worker if isinstance(worker, dict) else {}
    verified = worker.get("latestVerifiedAttempt")
    verified = verified if isinstance(verified, dict) else {}
    result["archive"] = {
        "latestVerifiedState": ("verified" if verified.get("status") == "verified"
                                else "not-observed"),
        "verifiedAt": _clock(verified.get("updatedAt")),
        "restoreVerified": verified.get("restoreVerified") is True,
        "remoteDownloadVerified": verified.get("remoteDownloadVerified") is True,
        "encryptionVerified": verified.get("encryptionVerified") is True,
        "encryptionVersion": _ENCRYPTION if (
            verified.get("encryptionVersion") == _ENCRYPTION) else None,
        "recoveryKeyVerified": verified.get("recoveryKeyVerified") is True,
        "restoreIsolationVerified": verified.get("restoreIsolation") ==
                                   "separate-database-instance",
        "sourceScopeVerified": verified.get("scope") ==
                               "reviewed-evidence-tables-not-full-database-backup",
        "deletionPermitted": False,
        "scope": "persisted-receipt-projection-not-offline-escrow-proof"
    }
    preview = storage.get("decisionProductsPreview")
    preview = preview if isinstance(preview, dict) else {}
    result["referencePreview"] = {
        "status": _choice(preview.get("status"),
                          frozenset(("sampled", "not-observed")), "not-observed"),
        "backupProofState": _choice(preview.get("backupProofState"), _PROOF_STATES,
                                    "not-observed"),
        "scannedRows": _number(preview.get("scannedRows"), integer=True,
                               maximum=20),
        "eligibleRows": _number(preview.get("eligibleRows"), integer=True,
                                maximum=20),
        "distinctProductArrays": _number(
            preview.get("distinctProductArrays"), integer=True, maximum=20),
        "sharedArrayRows": _number(
            preview.get("sharedArrayRows"), integer=True, maximum=20),
        "originalJsonBytes": _number(
            preview.get("originalJsonBytes"), integer=True, maximum=10**8),
        "referenceJsonBytes": _number(
            preview.get("referenceJsonBytes"), integer=True, maximum=10**8),
        "sampleJsonByteDifference": _number(
            preview.get("sampleJsonByteDifference"), integer=True, maximum=10**8),
        "manualRunAuthorized": False,
        "diskBytesFreed": None
    }
    pilot = storage.get("decisionProductsPilot")
    pilot = pilot if isinstance(pilot, dict) else {}
    result["pilot"] = {
        "status": _choice(pilot.get("status"), _PILOT_STATES, "not-observed"),
        "movedRows": _number(pilot.get("movedRows"), integer=True,
                             maximum=1),
        "diskBytesFreed": None
    }
    return result
