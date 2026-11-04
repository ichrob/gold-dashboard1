"""No private data leaks or false physical-savings claims in storage projections."""
import json
import unittest

import bob_diagnostics
import bob_mcp
import storage_brief


class StorageBriefTests(unittest.TestCase):
    def source(self):
        return {
            "status": "observed",
            "databaseBytes": 560838335,
            "configuredAllocationBytes": 1000000000,
            "budgetState": "caution",
            "lastSampleAt": 1793673000,
            "relationGrowthStatus": "observed",
            "largestTables": [
                {"table": "bob_diagnostic_history", "bytes": 45_000_000,
                 "private": "PRIVATE-ROW"},
                {"table": "bob_decision_audit", "bytes": 30_000_000},
                {"table": "bob_oauth_secrets", "bytes": 999_999_999},
                {"table": "bob_metric_checks", "bytes": 16_000_000},
                {"table": "bob_decision_outcomes", "bytes": 8_000_000}
            ],
            "largestTableDeltas": [
                {"table": "bob_diagnostic_history", "bytesDelta": 2_500_000},
                {"table": "bob_improvement_observations", "bytesDelta": -300_000},
                {"table": "bob_decision_audit", "bytesDelta": 700_000},
                {"table": "bob_secret_keys", "bytesDelta": 900_000_000},
                {"table": "bob_metric_checks", "bytesDelta": 100_000}
            ],
            "sensitiveToken": "PRIVATE-SECRET-NEVER-EMIT",
            "renderVolume": {
                "status": "observed", "resource": "dpg-private-ID",
                "unit": "bytes", "observedAt": 1793673100.0,
                "diskUsage": 669400000.0, "apiToken": "PRIVATE-SECRET"},
            "archiveWorker": {
                "status": "ready", "driveFileId": "secret-drive-id",
                "latestVerifiedAttempt": {
                    "status": "verified",
                    "updatedAt": "2026-11-03T01:49:30+00:00",
                    "restoreVerified": True,
                    "remoteDownloadVerified": True,
                    "encryptionVerified": True,
                    "encryptionVersion": "aes-256-gcm-stream-v1",
                    "recoveryKeyVerified": False,
                    "restoreIsolation": "separate-database-instance",
                    "scope": "reviewed-evidence-tables-not-full-database-backup",
                    "original": "PRIVATE-ORIGINAL-DO-NOT-EMIT"}},
            "decisionProductsPreview": {
                "status": "sampled", "backupProofState": "recovery-or-archive-proof-missing",
                "scannedRows": 20, "eligibleRows": 1,
                "distinctProductArrays": 1, "sharedArrayRows": 0,
                "originalJsonBytes": 9000, "referenceJsonBytes": 700,
                "sampleJsonByteDifference": 8300,
                "privateIsin": "SENSITIVE-ISIN",
                "manualRunAuthorized": False},
            "decisionProductsPilot": {
                "status": "no-attempt", "movedRows": 0, "errorText": "SECRET"},
            "hugeHistory": ["PRIVATE-HISTORY"*6000]
        }

    def test_allowlisted_storage_outcome_and_source_clock(self):
        view = storage_brief.project(self.source())
        self.assertEqual(view["status"], "observed")
        self.assertEqual(view["databaseBytes"], 560838335)
        self.assertEqual(view["largestTables"], [
            {"table": "bob_diagnostic_history", "allocatedBytes": 45_000_000},
            {"table": "bob_decision_audit", "allocatedBytes": 30_000_000},
            {"table": "bob_metric_checks", "allocatedBytes": 16_000_000}])
        self.assertEqual(view["largestGrowingTables"], [
            {"table": "bob_diagnostic_history", "allocatedBytesDelta": 2_500_000},
            {"table": "bob_decision_audit", "allocatedBytesDelta": 700_000},
            {"table": "bob_metric_checks", "allocatedBytesDelta": 100_000}])
        self.assertEqual(view["renderVolume"]["usedBytes"], 669400000)
        self.assertEqual(view["renderVolume"]["observedAt"], 1793673100.0)
        self.assertEqual(view["archive"]["latestVerifiedState"], "verified")
        self.assertTrue(view["archive"]["restoreVerified"])
        self.assertFalse(view["archive"]["recoveryKeyVerified"])
        self.assertFalse(view["archive"]["deletionPermitted"])
        self.assertEqual(view["referencePreview"]["backupProofState"],
                         "recovery-or-archive-proof-missing")
        self.assertFalse(view["referencePreview"]["manualRunAuthorized"])
        self.assertEqual(view["referencePreview"]["sampleJsonByteDifference"], 8300)
        self.assertEqual(view["referencePreview"]["distinctProductArrays"], 1)
        self.assertIsNone(view["referencePreview"]["diskBytesFreed"])
        self.assertIsNone(view["physicalBytesFreed"])
        self.assertIsNone(view["pilot"]["diskBytesFreed"])
        compact = json.dumps(view)
        self.assertLess(len(compact), 7500)
        for secret in ("PRIVATE", "SENSITIVE-ISIN", "secret-drive-id", "dpg-private-ID"):
            self.assertNotIn(secret, compact)

    def test_old_list_review_is_redacted_and_cannot_authorize_delete(self):
        source = self.source()
        source["androidImageAgeReview"] = {
            "status": "sampled", "readOnly": True, "hotZurichCalendarDays": 2,
            "sampledOldBatches": 4, "olderBatchesMayExist": False,
            "protectedProductOrExampleBatches": 2,
            "protectedReferenceBatches": 1,
            "protectedActiveOcrBatches": 0,
            "reviewOldFailedOriginalBatches": 1,
            "unknownPreservedBatches": 0,
            "oldImageDeletionAuthorized": True,
            "privateBatch": "PRIVATE-BATCH", "deviceToken": "PRIVATE-DEVICE",
            "physicalBytesFreed": 123456789}
        result = storage_brief.project(source)["androidImageAgeReview"]
        self.assertEqual(result["hotZurichCalendarDays"], 2)
        self.assertEqual(result["sampledOldBatches"], 4)
        self.assertEqual(result["reviewOldFailedOriginalBatches"], 1)
        self.assertEqual(result["protectedProductOrExampleBatches"], 2)
        self.assertFalse(result["oldImageDeletionAuthorized"])
        self.assertIsNone(result["physicalBytesFreed"])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_historical_evaluation_counters_never_grant_deletion(self):
        source = self.source()
        source["historyEvaluations"] = {
            "status":"observed",
            "areas":{"diagnoses":{"processedRows":400,"privateId":"SECRET"},
                     "decisions":{"processedRows":12}},
            "deletionAuthorized":True,
            "physicalBytesFreed":999999999}
        value = storage_brief.project(source)["historyEvaluations"]
        self.assertEqual(value["processedRows"],{"diagnoses":400,"decisions":12})
        self.assertFalse(value["deletionAuthorized"])
        self.assertIsNone(value["physicalBytesFreed"])
        self.assertNotIn("SECRET",json.dumps(value))

    def test_paper_daily_evaluation_never_claims_broker_gain(self):
        source = self.source()
        source["paperDailyEvaluations"] = {
            "status":"observed","processedReceipts":13,
            "grossModelOnly":False,"netProfitVerified":True,
            "fullHistoryVerified":True,"deletionAuthorized":True,
            "physicalBytesFreed":2222,"privateCase":"SECRET"}
        result = storage_brief.project(source)["paperDailyEvaluations"]
        self.assertEqual(result["processedReceipts"],13)
        self.assertTrue(result["grossModelOnly"])
        self.assertFalse(result["netProfitVerified"])
        self.assertFalse(result["fullHistoryVerified"])
        self.assertFalse(result["deletionAuthorized"])
        self.assertIsNone(result["physicalBytesFreed"])
        self.assertNotIn("SECRET",json.dumps(result))

    def test_quality_eval_is_private_and_never_represented_as_success(self):
        source = self.source()
        source["qualityEvaluations"] = {
            "status": "observed", "processedRecords": 256,
            "metricPassVerified": True, "fullHistoryVerified": True,
            "deletionAuthorized": True, "physicalBytesFreed": 9999999,
            "secretOriginal": "PRIVATE_METRIC_KEY"}
        result = storage_brief.project(source)["qualityEvaluations"]
        self.assertEqual(result["processedRecords"], 256)
        self.assertFalse(result["metricPassVerified"])
        self.assertFalse(result["fullHistoryVerified"])
        self.assertFalse(result["deletionAuthorized"])
        self.assertIsNone(result["physicalBytesFreed"])
        self.assertNotIn("PRIVATE_METRIC_KEY",json.dumps(result))

    def test_latest_attempt_exposes_only_fixed_redacted_failure_phase(self):
        source = self.source()
        source["archiveWorker"]["latestPersistedAttempt"] = {
            "status": "failed", "updatedAt": "2026-11-04T00:47:00+00:00",
            "phase": "verify-independent-recovery-key",
            "errorType": "ValueError",
            "receiptPersistenceErrorType": None,
            "attempt": "encrypted_recovery_private_identifier",
            "receipt": {"privateDriveId": "private-drive-id",
                        "token": "PRIVATE-TOKEN"},
        }
        view = storage_brief.project(source)
        current = view["archive"]["latestPersistedAttempt"]
        self.assertEqual(current["status"], "failed")
        self.assertEqual(current["phase"], "verify-independent-recovery-key")
        self.assertTrue(current["phaseRecorded"])
        self.assertEqual(current["errorType"], "ValueError")
        self.assertEqual(current["updatedAt"],
                         "2026-11-04T00:47:00+00:00")
        self.assertTrue(current["readOnly"])
        self.assertFalse(view["archive"]["recoveryKeyVerified"])
        self.assertFalse(view["decisionProductPilotAuthorized"])
        self.assertFalse(view["archive"]["deletionPermitted"])
        compact = json.dumps(view)
        for secret in ("private-drive-id", "PRIVATE-TOKEN",
                       "encrypted_recovery_private_identifier"):
            self.assertNotIn(secret, compact)

        source["archiveWorker"]["latestPersistedAttempt"].update(
            phase="token=PRIVATE-TOKEN", errorType="Secret=PRIVATE-TOKEN")
        unknown = storage_brief.project(source)["archive"]["latestPersistedAttempt"]
        self.assertIsNone(unknown["phase"])
        self.assertTrue(unknown["phaseRecorded"])
        self.assertIsNone(unknown["errorType"])
        source["archiveWorker"]["latestPersistedAttempt"]["phase"] = None
        self.assertFalse(storage_brief.project(source)["archive"]
                         ["latestPersistedAttempt"]["phaseRecorded"])

    def test_archive_status_requires_persisted_recovery_proof_and_age(self):
        source = self.source()
        source["observedAt"] = 1793673000
        view = storage_brief.project(source)
        self.assertEqual(view["archive"]["recoveryAcceptanceState"],
                         "persisted-recovery-proof-missing")
        self.assertFalse(view["archive"]["recoveryKeyVerified"])
        self.assertFalse(view["archive"]["deletionPermitted"])
        self.assertFalse(view["decisionProductPilotAuthorized"])

        # A chat, phone, or GitHub issue assertion cannot forge the
        # persisted archive receipt from Bob's primary database.
        source["offlineEmailRestored"] = True
        source["operatorConfirmedRecovery"] = True
        self.assertEqual(storage_brief.project(source)["archive"]
                         ["recoveryAcceptanceState"],
                         "persisted-recovery-proof-missing")

        receipt = source["archiveWorker"]["latestVerifiedAttempt"]
        receipt["recoveryKeyVerified"] = True
        self.assertEqual(storage_brief.project(source)["archive"]
                         ["recoveryAcceptanceState"],
                         "persisted-recovery-proof-fresh")
        self.assertFalse(storage_brief.project(source)["decisionProductPilotAuthorized"])

        source["observedAt"] = 1793673000 + 7*3600
        self.assertEqual(storage_brief.project(source)["archive"]
                         ["recoveryAcceptanceState"],
                         "persisted-proof-not-fresh")
        source["observedAt"] = None
        self.assertEqual(storage_brief.project(source)["archive"]
                         ["recoveryAcceptanceState"],
                         "proof-age-not-verified")
        receipt["encryptionVersion"] = "bad"
        self.assertEqual(storage_brief.project(source)["archive"]
                         ["recoveryAcceptanceState"],
                         "archive-receipt-incomplete")

    def test_render_http_diagnostics_are_numeric_and_not_pilot_approval(self):
        for code in (401, 403, 429, 500, 123, True, '401'):
            with self.subTest(code=code):
                source = self.source()
                source['renderVolume'] = {
                    'status': 'provider-http-error', 'httpStatus': code,
                    'apiToken': 'PRIVATE-SECRET'}
                view = storage_brief.project(source)
                self.assertEqual(view['renderVolume']['status'], 'provider-http-error')
                self.assertEqual(view['renderVolume']['providerHttpStatus'],
                                 code if type(code) is int and code in
                                 (400, 401, 403, 404, 409, 429, 500, 502, 503) else None)
                self.assertIsNone(view['renderVolume']['usedBytes'])
                self.assertFalse(view['decisionProductPilotAuthorized'])
                self.assertNotIn('PRIVATE-SECRET', json.dumps(view))

    def test_unsafe_provider_units_and_receipt_fields_fail_closed(self):
        item = self.source()
        item["renderVolume"]["unit"] = "mystery"
        item["archiveWorker"]["latestVerifiedAttempt"]["encryptionVersion"] = "bad-version"
        item["decisionProductsPreview"]["eligibleRows"] = 900
        item["decisionProductsPreview"]["sampleJsonByteDifference"] = -20
        view = storage_brief.project(item)
        self.assertEqual(view["renderVolume"]["status"], "invalid-or-unverified-units")
        self.assertIsNone(view["renderVolume"]["usedBytes"])
        self.assertIsNone(view["archive"]["encryptionVersion"])
        self.assertIsNone(view["referencePreview"]["eligibleRows"])
        self.assertIsNone(view["referencePreview"]["sampleJsonByteDifference"])
        self.assertFalse(view["decisionProductPilotAuthorized"])
        self.assertEqual(storage_brief.project(None)["status"], "not-observed")

    def test_render_http_diagnostic_is_redacted_and_never_authorizes_writes(self):
        for code in (401, 403, 404, 429, 503, 418, '403'):
            with self.subTest(code=code):
                source = self.source()
                source['renderVolume'] = {
                    'status': 'provider-http-error',
                    'httpStatus': code,
                    'apiToken': 'PRIVATE-SECRET-NEVER-EMIT',
                    'diskUsage': 123, 'unit': 'bytes',
                    'observedAt': 1793673100.0,
                }
                view = storage_brief.project(source)
                volume = view['renderVolume']
                self.assertEqual(volume['status'], 'provider-http-error')
                self.assertEqual(volume['providerHttpStatus'],
                                 code if type(code) is int and code in (400,401,403,404,409,429,500,502,503) else None)
                self.assertIsNone(volume['usedBytes'])
                self.assertIsNone(volume['observedAt'])
                self.assertIsNone(volume['unit'])
                self.assertFalse(view['decisionProductPilotAuthorized'])
                self.assertFalse(view['archive']['deletionPermitted'])
                self.assertNotIn('PRIVATE-SECRET', json.dumps(view))
        source['renderVolume'] = {'status': 'network-unavailable'}
        self.assertEqual(storage_brief.project(source)['renderVolume']['status'],
                         'network-unavailable')

    def test_growth_requires_real_snapshots_and_invalid_sizes_are_filtered(self):
        source = self.source()
        source["relationGrowthStatus"] = "needs-two-fixed-snapshots"
        source["largestTables"] = [
            {"table": "bob_metric_checks", "bytes": True},
            {"table": "bob_decision_audit", "bytes": -10},
            {"table": "bob_diagnostic_history", "bytes": 1.5},
            {"table": "bob_oauth_secrets", "bytes": 100},
            {"table": "bob_android_list_images", "bytes": 12_345},
            {"table": "bob_android_list_images", "bytes": 12_345},
        ]
        result = storage_brief.project(source)
        self.assertEqual(result["largestTables"], [
            {"table": "bob_android_list_images", "allocatedBytes": 12_345}])
        self.assertEqual(result["largestGrowingTables"], [])
        self.assertIsNone(result["physicalBytesFreed"])
        self.assertFalse(result["decisionProductPilotAuthorized"])

    def test_layout_breakdown_requires_valid_sums(self):
        source = self.source()
        source["layout"] = {"status": "observed", "tables": [
            {"table": "bob_diagnostic_history", "totalBytes": 1000,
             "heapBytes": 400, "indexBytes": 300, "toastBytes": 200,
             "otherBytes": 100},
            {"table": "bob_decision_audit", "totalBytes": 1000,
             "heapBytes": 400, "indexBytes": 300, "toastBytes": 200,
             "otherBytes": 99},
        ]}
        result = storage_brief.project(source)
        self.assertEqual(len(result["largestTableBreakdown"]), 1)
        self.assertEqual(result["largestTableBreakdown"][0]["indexBytes"], 300)
        self.assertIsNone(result["physicalBytesFreed"])
        source["layout"]["status"] = "not-observed"
        self.assertEqual(storage_brief.project(source)["largestTableBreakdown"], [])

    def test_diagnostic_equality_is_read_only(self):
        source = self.source()
        source["layout"] = {"diagnosticPayloadEqualitySample": {
            "status": "sampled", "stages": [{
                "stage": "input", "sampledRows": 20,
                "repeatedStoredJsonbRows": 5,
                "sameTraceTimeAndJsonbExtraRows": 2}]}}
        result = storage_brief.project(source)
        self.assertEqual(result["diagnosticEqualityStatus"], "sampled")
        self.assertEqual(result["diagnosticEqualityStages"][0]["equalPayloadExtraRows"], 5)
        self.assertTrue(result["diagnosticEqualityReadOnly"])
        self.assertIsNone(result["diagnosticEqualityDiskBytesFreed"])
        self.assertIsNone(result["physicalBytesFreed"])

    def test_diagnostic_byte_aggregate_no_physical_claim(self):
        source = self.source()
        source["layout"] = {"diagnosticPayloadByteSample": {
            "status": "sampled", "sampledInputRows": 10,
            "distinctPayloads": 3, "originalPayloadJsonBytes": 900,
            "sharedPayloadJsonBytes": 300,
            "payloadOnlyLogicalDifferenceBytes": 600}}
        result = storage_brief.project(source)["diagnosticByteSample"]
        self.assertEqual(result["payloadOnlyLogicalDifferenceBytes"], 600)
        self.assertIsNone(result["physicalBytesFreed"])
        source["layout"]["diagnosticPayloadByteSample"]["sharedPayloadJsonBytes"] = 999
        self.assertEqual(storage_brief.project(source)["diagnosticByteSample"]["status"],
                         "not-observed")

    def test_oversized_storage_omission_still_keeps_small_brief(self):
        source = self.source()
        report = bob_diagnostics.collect({"storage": lambda: source})
        self.assertEqual(report["areas"]["storageBrief"]["databaseBytes"], 560838335)
        bounded = bob_diagnostics.bounded_report(report, max_bytes=8000)
        self.assertEqual(bounded["areas"]["storage"]["reason"],
                         "omitted-response-size-limit")
        self.assertEqual(bounded["areas"]["storageBrief"]["databaseBytes"], 560838335)
        self.assertFalse(bounded["areas"]["storageBrief"]["archive"]["recoveryKeyVerified"])
        self.assertNotIn("PRIVATE-ORIGINAL", json.dumps(bounded))
        focused = bob_diagnostics.focused_report(report, "storage")
        self.assertEqual(list(focused["areas"]), ["storageBrief"])
        self.assertLess(len(json.dumps(focused)), 7500)

    def test_invalid_focus_and_tool_schema_remain_restricted(self):
        self.assertIn("storage", bob_diagnostics.DIAGNOSTIC_FOCUS)
        tools = bob_mcp.tool_definitions(diagnostics=True)
        definition = next(t for t in tools if t["name"] == "bob_diagnostics")
        self.assertIn("storage", definition["inputSchema"]["properties"]
                      ["focus"]["enum"])
        self.assertTrue(definition["annotations"]["readOnlyHint"])
        self.assertFalse(definition["annotations"]["destructiveHint"])
        with self.assertRaises(ValueError):
            bob_diagnostics.focused_report({}, "unapproved-private-section")


if __name__ == "__main__":
    unittest.main()
