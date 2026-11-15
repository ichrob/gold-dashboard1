"""Persisted provider classification survives both read-only redaction layers."""
import json
import unittest
from unittest.mock import patch
import storage_budget
import storage_brief

class RestoreTargetProjectionTests(unittest.TestCase):
    def project(self, proof, status="verified"):
        row = (status, "2026-11-15T00:41:02+00:00", {"receipt": proof})
        safe = storage_budget._sanitized_archive_attempt(row)
        source = {"archiveWorker": {"latestVerifiedAttempt": safe}}
        with patch.dict("os.environ", {"BOB_ARCHIVE_RESTORE_DATABASE_URL":
                                      "postgres://private-current-aiven-host"}):
            return storage_brief.project(source)["archive"]

    def test_stored_target_survives_without_private_identifiers(self):
        view = self.project({"restoreTargetPolicy": "aiven-uri-validated",
                             "driveFileId": "PRIVATE-FILE",
                             "restoreDsn": "PRIVATE-DSN"})
        self.assertEqual(view["restoreTargetPolicy"], "aiven-uri-validated")
        self.assertNotIn("PRIVATE", json.dumps(view))
        self.assertFalse(view["deletionPermitted"])
        self.assertEqual(view["recoveryAcceptanceState"], "archive-receipt-incomplete")

    def test_missing_and_unknown_receipts_never_inherit_current_configuration(self):
        for value in (None, "", "PRIVATE-DSN", True, {}, []):
            with self.subTest(value=value):
                self.assertIsNone(self.project({"restoreTargetPolicy": value})[
                    "restoreTargetPolicy"])
        self.assertIsNone(self.project({})["restoreTargetPolicy"])

    def test_other_target_is_not_promoted_to_aiven(self):
        self.assertEqual(self.project({"restoreTargetPolicy": "other-or-unverified"})[
            "restoreTargetPolicy"], "other-or-unverified")

if __name__ == "__main__":
    unittest.main()
