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
        self.assertLess(len(compact), 3500)
        for secret in ("PRIVATE", "SENSITIVE-ISIN", "secret-drive-id", "dpg-private-ID"):
            self.assertNotIn(secret, compact)

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
        self.assertLess(len(json.dumps(focused)), 3500)

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
