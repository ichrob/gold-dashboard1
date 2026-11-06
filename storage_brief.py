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
                            "configuration-required", "invalid-response", "provider-http-error",
                            "network-unavailable"))
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



_ARCHIVE_PHASES = frozenset((
    "drive-preflight", "restore-isolation-check", "export", "local-restore",
    "encrypt-before-upload", "encrypted-upload", "encrypted-download",
    "authenticated-decrypt", "verify-independent-recovery-key", "upload",
    "download", "remote-restore", "receipt-upload",
))
_ARCHIVE_ATTEMPT_STATES = frozenset((
    "verified", "failed", "running", "already-attempted-today",
    "blocked", "ready", "disabled",
))
_ARCHIVE_ERROR_TYPES = frozenset((
    "ValueError", "TypeError", "RuntimeError", "TimeoutError", "OSError",
    "PermissionError", "ConnectionError", "OperationalError", "DatabaseError",
    "InterfaceError", "ProgrammingError", "LockNotAvailable", "QueryCanceled",
    "InvalidTag", "KeyError",
))


def _persisted_attempt_brief(item):
    """Only fixed, nonsecret fields from the already-read durable archive row.

    The claim identifier and raw receipt are intentionally absent. A null
    phase means missing or unrecognized; phaseRecorded distinguishes the two.
    No new SQL, log lookup, file access or archive action is performed.
    """
    item = item if type(item) is dict else {}
    return {
        "status": _choice(item.get("status"), _ARCHIVE_ATTEMPT_STATES,
                          "not-observed"),
        "updatedAt": _clock(item.get("updatedAt")),
        "phase": _choice(item.get("phase"), _ARCHIVE_PHASES, None),
        "phaseRecorded": type(item.get("phase")) is str,
        "errorType": _choice(item.get("errorType"), _ARCHIVE_ERROR_TYPES, None),
        "receiptPersistenceErrorType": _choice(
            item.get("receiptPersistenceErrorType"), _ARCHIVE_ERROR_TYPES, None),
        "readOnly": True,
    }


def _persisted_archive_gate(archive, observed_at):
    """Read-only acceptance status from Bob's stored archive receipt ONLY.

    An externally witnessed/offline recovery or chat screenshot is not a
    persisted recovery root proof, and no status here authorizes a write.
    """
    required = ("restoreVerified", "remoteDownloadVerified",
                "encryptionVerified", "restoreIsolationVerified",
                "sourceScopeVerified")
    if (archive.get("latestVerifiedState") != "verified" or
            archive.get("encryptionVersion") != _ENCRYPTION or
            any(archive.get(key) is not True for key in required)):
        return "archive-receipt-incomplete"
    if archive.get("recoveryKeyVerified") is not True:
        return "persisted-recovery-proof-missing"
    stamp = archive.get("verifiedAt")
    when = _number(observed_at, maximum=10**11)
    if stamp is None or when is None:
        return "proof-age-not-verified"
    from datetime import datetime
    try:
        age = when - datetime.fromisoformat(stamp).timestamp()
    except (TypeError, ValueError, OverflowError):
        return "proof-age-not-verified"
    if not 0 <= age <= 6 * 3600:
        return "persisted-proof-not-fresh"
    return "persisted-recovery-proof-fresh"


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
    if type(storage.get("featureAllocation")) is dict:
        from feature_storage import project as feature_allocation
        result["featureAllocation"] = feature_allocation(
            storage["featureAllocation"], storage.get("observedAt"))
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

    byte_sample = layout.get("diagnosticPayloadByteSample")
    byte_sample = byte_sample if isinstance(byte_sample, dict) else {}
    byte_fields = ("sampledInputRows", "distinctPayloads",
                   "originalPayloadJsonBytes", "sharedPayloadJsonBytes",
                   "payloadOnlyLogicalDifferenceBytes")
    valid_bytes = byte_sample.get("status") == "sampled"
    numbers = [byte_sample.get(key) for key in byte_fields]
    valid_bytes = valid_bytes and all(type(v) is int and 0 <= v <= 10**9
                                      for v in numbers)
    if valid_bytes:
        valid_bytes = (numbers[0] <= 256 and numbers[1] <= numbers[0]
                       and numbers[3] <= numbers[2]
                       and numbers[4] == numbers[2]-numbers[3])
    result["diagnosticByteSample"] = (
        dict(zip(byte_fields, numbers), status="sampled",
             physicalBytesFreed=None, readOnly=True)
        if valid_bytes else {"status": "not-observed",
                             "physicalBytesFreed": None, "readOnly": True})

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
        "providerHttpStatus": (provider.get("httpStatus")
                               if kind == "provider-http-error" and
                                  type(provider.get("httpStatus")) is int and
                                  provider["httpStatus"] in (400, 401, 403, 404, 409, 429, 500, 502, 503)
                               else None),
        "observedAt": observed if valid else None,
        "unit": "bytes" if valid else None,
        "scope": "physical-provider-volume-single-observation-not-savings"
    }

    cold_tests = storage.get("coldTests")
    cold_tests = cold_tests if isinstance(cold_tests, dict) else {}
    cycle = cold_tests.get("lastCycle")
    cycle = cycle if isinstance(cycle, dict) else {}
    result["coldTests"] = {
        "status": cold_tests.get("status") if cold_tests.get("status") in
                  ("observed", "not-observed") else "not-observed",
        "offloadedRows": _number(cold_tests.get("offloadedRows"), maximum=10**12),
        "logicalJsonBytesReduced": _number(cold_tests.get("logicalJsonBytesReduced"), maximum=10**12),
        "lastVerifiedAt": _clock(cold_tests.get("lastVerifiedAt")),
        "lastCycleStatus": cycle.get("status") if cycle.get("status") in
            ("not-run", "busy", "archive-running", "backup-proof-not-fresh",
             "verified-offload", "no-eligible-rows", "deferred") else "not-observed",
        "physicalBytesFreed": None,
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
    # This projected gate is explanatory only. It cannot mark operator
    # evidence as persisted, cannot call archival services, and is never
    # consumed by the one-row writer's independent _proof_state check.
    result["archive"]["recoveryAcceptanceState"] = _persisted_archive_gate(
        result["archive"], storage.get("observedAt"))
    # The last attempted run is distinct from the last *successful* archive.
    # It cannot lift any pilot, deletion or proof gate.
    result["archive"]["latestPersistedAttempt"] = _persisted_attempt_brief(
        worker.get("latestPersistedAttempt"))
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
    # Two-day hot-image preference is a READ-ONLY age review. An older
    # original may contain a unique KO/venue fact or useful OCR example;
    # neither this sample nor any evaluation grants automatic deletion.
    age = storage.get("androidImageAgeReview")
    age = age if type(age) is dict else {}
    age_state = _choice(age.get("status"),
        frozenset(("sampled", "observed-empty", "busy", "not-observed")),
        "not-observed")
    result["androidImageAgeReview"] = {
        "status": age_state, "readOnly": True,
        "hotZurichCalendarDays": 2,
        "sampledOldBatches": _number(
            age.get("sampledOldBatches"), integer=True, maximum=24),
        "olderBatchesMayExist": age.get("olderBatchesMayExist") is True,
        "protectedProductOrExampleBatches": _number(
            age.get("protectedProductOrExampleBatches"),
            integer=True, maximum=24),
        "protectedReferenceBatches": _number(
            age.get("protectedReferenceBatches"), integer=True, maximum=24),
        "protectedActiveOcrBatches": _number(
            age.get("protectedActiveOcrBatches"), integer=True, maximum=24),
        "reviewOldFailedOriginalBatches": _number(
            age.get("reviewOldFailedOriginalBatches"), integer=True, maximum=24),
        "unknownPreservedBatches": _number(
            age.get("unknownPreservedBatches"), integer=True, maximum=24),
        "oldImageDeletionAuthorized": False,
        "physicalBytesFreed": None,
        "scope": "older-than-yesterday-review-not-batch-verified-offload"
    }
    # Source-reading backlog worker: scalar summaries only, never user IDs or
    # proof of a complete replay/backup. An evaluation is not deletion consent.
    hist = storage.get("historyEvaluations")
    hist = hist if type(hist) is dict else {}
    hist_areas = hist.get("areas")
    hist_areas = hist_areas if type(hist_areas) is dict else {}
    hist_counts = {}
    for area in ("diagnoses", "decisions"):
        item = hist_areas.get(area)
        item = item if type(item) is dict else {}
        hist_counts[area] = _number(item.get("processedRows"),
                                    integer=True, maximum=10**12)
    result["historyEvaluations"] = {
        "status": _choice(hist.get("status"),
                          frozenset(("warming", "observed", "not-observed")),
                          "not-observed"),
        "processedRows": hist_counts,
        "coverage": "forward-only-processed-not-full-replay",
        "deletionAuthorized": False,
        "physicalBytesFreed": None
    }
    # Compact gross-model-only paper evaluation state. Never equate signs
    # of model arithmetic to actual realised DEGIRO returns or safe deletion.
    paper_eval = storage.get("paperDailyEvaluations")
    paper_eval = paper_eval if type(paper_eval) is dict else {}
    result["paperDailyEvaluations"] = {
        "status": _choice(paper_eval.get("status"),
            frozenset(("observed", "warming", "not-observed")),
            "not-observed"),
        "processedReceipts": _number(paper_eval.get("processedReceipts"),
                                      integer=True, maximum=10**12),
        "grossModelOnly": True, "netProfitVerified": False,
        "fullHistoryVerified": False, "deletionAuthorized": False,
        "physicalBytesFreed": None,
    }
    # A compact forward-only assessment of already stored metric-source labels.
    # Cold pointers are not formula success, and no digest permits source deletion.
    quality_eval = storage.get("qualityEvaluations")
    quality_eval = quality_eval if type(quality_eval) is dict else {}
    result["qualityEvaluations"] = {
        "status": _choice(quality_eval.get("status"),
            frozenset(("observed", "warming", "not-observed")),
            "not-observed"),
        "processedRecords": _number(quality_eval.get("processedRecords"),
                                     integer=True, maximum=10**12),
        "metricPassVerified": False,
        "fullHistoryVerified": False,
        "deletionAuthorized": False,
        "physicalBytesFreed": None
    }
    # Forward-only improvement labels are not verified strategy learning.
    improvement_eval = storage.get("improvementEvaluations")
    improvement_eval = improvement_eval if type(improvement_eval) is dict else {}
    result["improvementEvaluations"] = {
        "status": _choice(improvement_eval.get("status"),
            frozenset(("observed", "warming", "not-observed")),
            "not-observed"),
        "processedRecords": _number(improvement_eval.get("processedRecords"),
                                    integer=True, maximum=10**12),
        "improvementVerified": False,
        "fullHistoryVerified": False,
        "deletionAuthorized": False,
        "physicalBytesFreed": None
    }
    pilot = storage.get("decisionProductsPilot")
    pilot = pilot if isinstance(pilot, dict) else {}
    result["pilot"] = {
        "status": _choice(pilot.get("status"), _PILOT_STATES, "not-observed"),
        "movedRows": _number(pilot.get("movedRows"), integer=True,
                             maximum=1),
        "diskBytesFreed": None
    }

    # Small independent projection; full storage diagnostics can exceed MCP
    # response limits. Never expose raw rows or impute missing fixed slots.
    fixed = storage.get("fixedSlotDaily")
    fixed = fixed if type(fixed) is dict and fixed.get("readOnly") is True else {}
    latest = fixed.get("latest")
    latest = latest if type(latest) is dict else {}
    daily_states = frozenset(("observed", "partial-relations",
        "missing-both-slots", "missing-baseline-slot",
        "missing-endpoint-slot", "no-valid-snapshots"))
    counter_states = frozenset(("observed-reset-unverified",
        "counter-decrease-reset-or-wrap", "missing-counter-snapshot",
        "relation-not-observed"))
    allowed = ("bob_diagnostic_history", "bob_candle_evidence",
               "bob_decision_audit", "bob_metric_checks",
               "bob_improvement_observations")

    def signed(value):
        return (value if type(value) is int and abs(value) <= 10**13 else None)

    detailed = []
    existing = latest.get("tables")
    existing = existing if type(existing) is list else []
    for name in allowed:
        item = next((r for r in existing if type(r) is dict
                     and r.get("table") == name), {})
        counts = item.get("writeCounters")
        counts = counts if type(counts) is dict else {}
        keys = ("inserted", "updated", "deleted", "hotUpdated")
        valid_counts = all(_number(counts.get(k), integer=True) is not None
                           for k in keys)
        detailed.append({
            "table": name,
            "allocatedBefore": _number(item.get("allocatedBytesBefore"), integer=True),
            "allocatedAfter": _number(item.get("allocatedBytesAfter"), integer=True),
            "netAllocated": signed(item.get("netAllocatedBytes")),
            "counterStatus": _choice(item.get("counterStatus"), counter_states,
                                     "missing-counter-snapshot"),
            "counters": ({k: counts[k] for k in keys} if valid_counts
                         and item.get("counterStatus") == "observed-reset-unverified"
                         else None),
        })
    previous = fixed.get("retrospective")
    previous = previous if type(previous) is list else []
    history = []
    for entry in previous[:7]:
        if type(entry) is not dict:
            continue
        values = entry.get("relationNetBytes")
        values = ([signed(x) for x in values] if type(values) is list
                  and len(values) == len(allowed) else [None] * len(allowed))
        history.append({
            "startSlot": _number(entry.get("startSlot"), integer=True, maximum=10**11),
            "endSlot": _number(entry.get("endSlot"), integer=True, maximum=10**11),
            "status": _choice(entry.get("status"), daily_states,
                              "no-valid-snapshots"),
            "dbDelta": signed(entry.get("databaseBytesDelta")),
            "tableDeltas": values,
            "counterTablesResetUnverified": _number(
                entry.get("observedCounterTablesResetUnverified"),
                integer=True, maximum=5),
            "counterDecreaseTables": _number(entry.get("counterDecreaseTables"),
                                             integer=True, maximum=5),
        })
    result["fixedSlotDaily"] = {
        "status": _choice(latest.get("status"), daily_states,
                          "no-valid-snapshots"),
        "startSlot": _number(latest.get("startSlot"), integer=True, maximum=10**11),
        "endSlot": _number(latest.get("endSlot"), integer=True, maximum=10**11),
        "dbBefore": _number(latest.get("databaseBytesBefore"), integer=True),
        "dbAfter": _number(latest.get("databaseBytesAfter"), integer=True),
        "dbDelta": signed(latest.get("databaseBytesDelta")),
        "tableOrder": list(allowed),
        "tables": detailed,
        "retrospectiveDays": history,
        "oldestLoadedSlot": _number(fixed.get("oldestLoadedSlot"),
                                   integer=True, maximum=10**11),
        "newestLoadedSlot": _number(fixed.get("newestLoadedSlot"),
                                   integer=True, maximum=10**11),
        "statsResetTimestamp": None,
        "statsResetVerified": False,
        "walBytesDelta": None,
        "bloatBytes": None,
        "renderVolumeBytesDelta": None,
        "diskBytesFreed": None,
        "readOnly": True,
        "scope": "exact-18-UTC-saved-slot-comparison-not-physical-volume",
    }

    # Exact scalar comparison footprint.  Historical component deltas stay
    # null until both fixed endpoint samples contain the dedicated measurement.
    entry = storage.get("entryExitStorage")
    entry = entry if type(entry) is dict and entry.get("readOnly") is True else {}
    if entry.get("status") != "observed":
        result["entryExitStorage"] = {
            "status": "not-observed", "readOnly": True,
            "physicalBytesFreed": None}
        return result
    window_states = frozenset(("observed", "missing-both-endpoints",
        "missing-baseline", "missing-endpoint", "relation-missing-at-endpoint"))
    component_states = frozenset(("observed", "needs-fixed-endpoint-measurement"))
    def footprint_window(value):
        value = value if type(value) is dict else {}
        parts = value.get("components")
        parts = parts if type(parts) is dict else {}
        deltas = parts.get("deltas") if type(parts.get("deltas")) is dict else {}
        fixed_keys = ("totalBytes", "heapBytes", "indexBytes", "toastBytes",
                      "otherBytes", "episodes", "completeEpisodes", "openEpisodes",
                      "archivedEpisodes", "logicalPayloadBytes",
                      "completeLogicalPayloadBytes", "openLogicalPayloadBytes")
        return {
            "status": _choice(value.get("status"), window_states, "missing-both-endpoints"),
            "exact": value.get("exact") is True,
            "zurichDate": value.get("zurichDate") if type(value.get("zurichDate")) is str
                and len(value["zurichDate"]) == 10 else None,
            "startSlot": _number(value.get("startSlot"), integer=True, maximum=10**11),
            "endSlot": _number(value.get("endSlot"), integer=True, maximum=10**11),
            "relationBytesBefore": _number(value.get("relationBytesBefore"), integer=True),
            "relationBytesAfter": _number(value.get("relationBytesAfter"), integer=True),
            "relationBytesDelta": signed(value.get("relationBytesDelta")),
            "databaseBytesBefore": _number(value.get("databaseBytesBefore"), integer=True),
            "databaseBytesAfter": _number(value.get("databaseBytesAfter"), integer=True),
            "databaseBytesDelta": signed(value.get("databaseBytesDelta")),
            "componentStatus": _choice(parts.get("status"), component_states,
                                       "needs-fixed-endpoint-measurement"),
            "componentDeltas": ({key:signed(deltas.get(key)) for key in fixed_keys}
                if parts.get("status") == "observed" else None),
        }
    current = entry.get("current")
    current = current if type(current) is dict else {}
    arm_statuses = entry.get("armStatuses")
    arm_statuses = arm_statuses if type(arm_statuses) is dict else {}
    current_keys = ("totalBytes", "heapBytes", "indexBytes", "toastBytes",
                    "otherBytes", "episodes", "completeEpisodes", "openEpisodes",
                    "archivedEpisodes", "logicalPayloadBytes",
                    "completeLogicalPayloadBytes", "openLogicalPayloadBytes")
    first_window = footprint_window(entry.get("firstCompletedTradeDay"))
    latest_window = footprint_window(entry.get("latestCompletedTradeDay"))
    result["entryExitStorage"] = {
        "status": "observed",
        "tradeWindow": "08:00-22:00 Europe/Zurich",
        "firstCompletedTradeDay": first_window,
        "latestCompletedTradeDay": (latest_window if latest_window.get("zurichDate")
            != first_window.get("zurichDate") else None),
        "current": {key:value for key in current_keys
                    if (value := _number(current.get(key), integer=True)) is not None},
        "armStatuses": {key:value for key in
            ("waiting","pending","open","exit-pending","closed","inconclusive","no-entry")
            if (value := _number(arm_statuses.get(key), integer=True,
                                 maximum=10**12)) is not None},
        "completeLogicalBytesPerCase": _number(entry.get("completeLogicalBytesPerCase")),
        "physicalBytesFreed": None, "renderVolumeBytesDelta": None,
        "readOnly": True,
        "scope": "fixed-half-hour-relation-allocation-and-current-redacted-scalars",
    }

    return result
