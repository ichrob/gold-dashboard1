"""Private storage readiness must never become an image backup trigger."""
import json
import os
import unittest
from unittest.mock import patch

import android_image_backup_readiness as readiness


class ReadinessTests(unittest.TestCase):
    def test_missing_runtime_config_sanitized(self):
        with patch.dict(os.environ, {}, clear=True):
            result = readiness.report()
        self.assertEqual(result["status"], "configuration-incomplete")
        self.assertFalse(result["privateArchiveConfigurationPresent"])
        self.assertFalse(result["imageEncryptionKeyPresent"])
        self.assertFalse(result["manualExecutionConfigurationComplete"])
        self.assertIsNone(result["remoteOriginalBatchBackupVerified"])
        self.assertIsNone(result["diskBytesFreed"])

    def test_ready_config_not_misreported_as_actual_archive(self):
        settings = {"DATABASE_URL": "postgres://user:VERY_PRIVATE@source/img",
                    "BOB_ARCHIVE_RESTORE_DATABASE_URL": "postgres://secret@target/restored",
                    "BOB_ARCHIVE_CREDENTIAL_SOURCE": "encrypted-store",
                    "BOB_ARCHIVE_PARENT_FOLDER_ID": "PRIVATE-FOLDER-ID",
                    "BOB_PNG_BACKUP_KEY_HEX": "af" * 32,
                    "BOB_PNG_BACKUP_EXPLICIT_ACK": "one-batch-only"}
        with patch.dict(os.environ, settings, clear=True), \
             patch("psycopg.connect", side_effect=AssertionError("DB forbidden")), \
             patch("android_image_backup_cli._execute",
                   side_effect=AssertionError("execution forbidden")), \
             patch("android_image_backup_cli._drive",
                   side_effect=AssertionError("Drive forbidden")):
            result = readiness.report()
        self.assertTrue(result["privateArchiveConfigurationPresent"])
        self.assertTrue(result["manualExecutionConfigurationComplete"])
        self.assertTrue(result["imageEncryptionKeyPresent"])
        self.assertFalse(result["originalImageMigrationAuthorized"])
        self.assertFalse(result["originalImageDeletionAuthorized"])
        self.assertIsNone(result["independentOriginalBatchRestoreVerified"])
        output=json.dumps(result)
        for secret in ("VERY_PRIVATE","PRIVATE-FOLDER-ID","af"*32, "postgres://"):
            self.assertNotIn(secret, output)

    def test_key_without_escrow_is_not_recovery_proof(self):
        with patch.dict(os.environ, {"BOB_PNG_BACKUP_KEY_HEX": "1d"*32}, clear=True):
            result=readiness.report()
        self.assertTrue(result["imageEncryptionKeyPresent"])
        self.assertFalse(result["manualExecutionConfigurationComplete"])
        self.assertIsNone(result["remoteOriginalBatchBackupVerified"])

    def test_exception_fails_to_not_observed(self):
        with patch("android_image_backup_cli.configuration",
                   side_effect=ValueError("secret:DO-NOT-LEAK")):
            result=readiness.report()
        self.assertEqual(result["status"],"not-observed")
        self.assertNotIn("DO-NOT-LEAK", str(result))
        self.assertFalse(result["originalImageDeletionAuthorized"])


if __name__=="__main__":
    unittest.main()
