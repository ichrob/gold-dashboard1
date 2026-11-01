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



class CandidateReadOnlyTests(unittest.TestCase):
    def test_true_false_are_only_from_bounded_existence_query(self):
        from contextlib import nullcontext
        class Fake:
            def __init__(self, answer):
                self.answer=answer
                self.sql=[]
            def transaction(self):return nullcontext()
            def execute(self, query):
                self.sql.append(query)
                return self
            def fetchone(self):return (self.answer,)
        for answer in (True,False):
            with self.subTest(answer=answer):
                db=Fake(answer)
                self.assertIs(readiness.synced_source_candidate_present(db),answer)
                self.assertEqual(len(db.sql),3)
                self.assertTrue(all(q.startswith('SET LOCAL') or q.lstrip().startswith('SELECT') for q in db.sql))
                self.assertIn('NOT d.revoked',db.sql[-1])
                self.assertIn('LIMIT 1',db.sql[-1])
                self.assertNotIn('i.payload',db.sql[-1])

    def test_missing_source_is_unknown_and_exception_is_redacted(self):
        from contextlib import nullcontext
        class Failing:
            def transaction(self):return nullcontext()
            def execute(self, sql):raise ValueError('private SQL detail')
        self.assertIsNone(readiness.synced_source_candidate_present(Failing()))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI integration')
class PostgresCandidateTests(unittest.TestCase):
    def test_synced_and_active_and_not_revoked(self):
        import psycopg
        import uuid
        schema='image_candidate_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                conn.execute("""CREATE TABLE bob_android_diagnostic_devices(
                    token_hash TEXT PRIMARY KEY, revoked BOOLEAN NOT NULL DEFAULT FALSE,
                    expires_at TIMESTAMPTZ NOT NULL)""")
                conn.execute("""CREATE TABLE bob_android_list_images(
                    batch_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    payload JSONB NOT NULL,parsed_items JSONB,import_receipt JSONB)""")
                conn.execute("""INSERT INTO bob_android_diagnostic_devices
                    VALUES('fake',FALSE,now()+interval '1 day')""")
                self.assertIs(readiness.synced_source_candidate_present(conn),False)
                conn.execute("""INSERT INTO bob_android_list_images
                    (batch_id,token_hash,payload,parsed_items,import_receipt)
                    VALUES ('synthetic','fake','{}'::jsonb,'[]'::jsonb,
                            '{"stage":"synced"}'::jsonb)""")
                self.assertIs(readiness.synced_source_candidate_present(conn),True)
                conn.execute("""UPDATE bob_android_diagnostic_devices SET revoked=TRUE
                    WHERE token_hash='fake'""")
                self.assertIs(readiness.synced_source_candidate_present(conn),False)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')

if __name__=="__main__":
    unittest.main()
