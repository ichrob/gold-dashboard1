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

# Fixed infrastructure relations only; never publish table names supplied by
# arbitrary receipts, credentials, uploaded files or a dynamic identifier.
_VISIBLE_RELATIONS = frozenset((
    "bob_decision_audit", "bob_decision_outcomes", "bob_diagnostic_history",
    "bob_improvement_observations", "bob_metric_checks", "bob_candle_evidence",
    "bob_test_repairs", "bob_list_price_pairs", "bob_future_predictions",
    "bob_cold_observation_objects", "bob_android_list_images",
))


def _relation_rows(source, *, key, value_key, output_key, positive_only=False):
    """At most three already-measured allocation observations, no extra SQL.

    Relation allocation/delta does not prove bloat or freed disk bytes.
    """
    rows = source.get(key)
    if type(rows) is not list:
        return []
    result, seen = [], set()
    for row in rows[:12]:
        if type(row) is not dict:
            continue
        name, value = row.get("table"), row.get(value_key)
        if (type(name) is not str or name not in _VISIBLE_RELATIONS
                or name in seen or type(value) is not int
                or abs(value) > 10**12
                or (positive_only and value <= 0)
                or (not positive_only and value < 0)):
            continue
        seen.add(name)
        result.append({"table": name, output_key: value})
        if len(result) == 3:
            break
    return result


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
    # Catalog observations already gathered by storage_budget.report; no
    # additional queries, no source data, no deletion/repack permission.
    result["largestTables"] = _relation_rows(
        storage, key="largestTables", value_key="bytes",
        output_key="allocatedBytes")
    result["largestGrowingTables"] = (
        _relation_rows(storage, key="largestTableDeltas",
                       value_key="bytesDelta", output_key="allocatedBytesDelta",
                       positive_only=True)
        if storage.get("relationGrowthStatus") == "observed" else [])

    # Already measured by storage_layout.report. Distinguish indexes and
    # TOAST from heap without new SQL or claiming reclaimable disk bytes.
    layout = storage.get("layout")
    layout = layout if type(layout) is dict and layout.get("status") == "observed" else {}
    layout_rows = layout.get("tables")
    breakdown = []
    if type(layout_rows) is list:
        for item in layout_rows[:12]:
            if type(item) is not dict or item.get("table") not in _VISIBLE_RELATIONS:
                continue
            values = [item.get(k) for k in ("totalBytes", "heapBytes",
                       "indexBytes", "toastBytes", "otherBytes")]
            if (any(type(v) is not int or not 0 <= v <= 10**12 for v in values)
                    or sum(values[1:]) != values[0]):
                continue
            breakdown.append({"table": item["table"], "totalBytes": values[0],
                              "heapBytes": values[1], "indexBytes": values[2],
                              "toastBytes": values[3], "otherBytes": values[4]})
            if len(breakdown) == 3:
                break
    result["largestTableBreakdown"] = breakdown

    layout = storage.get("layout")
    layout = layout if isinstance(layout, dict) else {}
    sample = layout.get("diagnosticPayloadEqualitySample")
    sample = sample if isinstance(sample, dict) else {}
    result["diagnosticEqualityStatus"] = _choice(
        sample.get("status"), frozenset(("sampled", "observed-empty")),
        "not-observed")
    rows = sample.get("stages") if sample.get("status") == "sampled" else None
    result["diagnosticEqualityStages"] = []
    if isinstance(rows, list):
        for row in rows[:2]:
            if not isinstance(row, dict) or row.get("stage") not in ("input", "analysis"):
                continue
            total = _number(row.get("sampledRows"), integer=True, maximum=256)
            equal = _number(row.get("repeatedStoredJsonbRows"), integer=True, maximum=256)
            same = _number(row.get("sameTraceTimeAndJsonbExtraRows"), integer=True, maximum=256)
            if total is None or equal is None or same is None or same > equal or equal >= total:
                continue
            result["diagnosticEqualityStages"].append({
                "stage": row["stage"], "sampledRows": total,
                "equalPayloadExtraRows": equal, "sameContextExtraRows": same})
    result["diagnosticEqualityReadOnly"] = True
    result["diagnosticEqualityDiskBytesFreed"] = None

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
