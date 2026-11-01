"""Manual PNG CLI: argument safety, private status, preflight, one-batch guard."""
import contextlib
import io
import json
import os
import unittest
from unittest.mock import patch

import android_image_backup_cli as cli

_ENV = {"DATABASE_URL": "postgres://private:do-not-log@source/image",
        "BOB_ARCHIVE_RESTORE_DATABASE_URL": "postgres://private:secret@target/restore",
        "BOB_ARCHIVE_CREDENTIAL_SOURCE": "encrypted-store",
        "BOB_ARCHIVE_PARENT_FOLDER_ID": "private-folder-id",
        "BOB_PNG_BACKUP_KEY_HEX": "3a"*32,
        "BOB_PNG_BACKUP_EXPLICIT_ACK": "one-batch-only"}


class _Row:
    def __init__(self,row):
        self.row=row
    def fetchone(self):
        return self.row


class _Conn:
    def __init__(self,row):
        self.row=row
        self.queries=[]
    def __enter__(self):
        return self
    def __exit__(self,*a):
        return False
    def execute(self,sql,*args):
        self.queries.append(sql)
        if sql.lstrip().startswith("SELECT"):
            return _Row(self.row)
        if sql.startswith("SET LOCAL"):
            return _Row(None)
        raise AssertionError("Unexpected write")


class CLIUnitTests(unittest.TestCase):
    def test_status_redacts_credentials_and_never_connects(self):
        output=io.StringIO()
        with patch.dict(os.environ,_ENV,clear=True),patch(
                "psycopg.connect",side_effect=AssertionError("status must not connect")), \
                contextlib.redirect_stdout(output):
            code=cli.main(["status"])
        self.assertEqual(code,0)
        value=json.loads(output.getvalue())
        self.assertEqual(value["status"],"ready")
        self.assertTrue(value["separateEncryptionKeyConfigured"])
        self.assertTrue(value["acknowledgementConfigured"])
        self.assertFalse(value["deletionAuthorized"])
        self.assertNotIn("do-not-log",output.getvalue())
        self.assertNotIn("secret",output.getvalue())
        self.assertNotIn("3a"*32,output.getvalue())

    def test_invalid_args_never_execute_or_echo_user_data(self):
        out=io.StringIO()
        with patch.object(cli,"_execute") as execute,contextlib.redirect_stdout(out):
            code=cli.main(["execute","--unexpected-private-token"])
        self.assertEqual(code,2)
        self.assertNotIn("unexpected-private-token",out.getvalue())
        execute.assert_not_called()

    def test_key_and_ack_missing_prevent_live_execution(self):
        for drop in ("BOB_PNG_BACKUP_KEY_HEX","BOB_PNG_BACKUP_EXPLICIT_ACK"):
            env=dict(_ENV)
            env.pop(drop)
            with self.subTest(drop=drop),patch.dict(os.environ,env,clear=True), \
                 patch.object(cli,"_latest_batch") as selector, \
                 patch.object(cli,"_drive") as drive:
                outcome=cli._execute()
                self.assertEqual(outcome["status"],"blocked")
                self.assertFalse(outcome["imageBackupExecuted"])
                selector.assert_not_called()
                drive.assert_not_called()

    def test_one_batch_select_only_read_query_and_device_binding(self):
        conn=_Conn(("1"*32,"a"*64))
        with patch("psycopg.connect",return_value=conn) as connect:
            chosen=cli._latest_batch("opaque-source")
        self.assertEqual(chosen,("1"*32,"a"*64))
        self.assertIn("default_transaction_read_only=on",connect.call_args.kwargs["options"])
        self.assertEqual(sum(x.strip().startswith("SELECT") for x in conn.queries),1)
        self.assertTrue(all(x.startswith("SET LOCAL") or x.strip().startswith("SELECT")
                            for x in conn.queries))
        self.assertIn("NOT d.revoked",conn.queries[-1])
        self.assertIn("i.import_receipt->>'stage'='synced'",conn.queries[-1])
        self.assertIn("LIMIT 1",conn.queries[-1])

    def test_no_active_complete_original_is_blocked(self):
        with patch("psycopg.connect",return_value=_Conn(None)):
            with self.assertRaises(LookupError):
                cli._latest_batch("opaque-source")

    def test_preflight_readonly_no_image_upload(self):
        from unittest.mock import MagicMock
        drive=MagicMock()
        with patch.dict(os.environ,_ENV,clear=True), \
             patch("drive_evidence_archive.verify_restore_isolation",
                   return_value="separate-database-instance"), \
             patch.object(cli,"_drive",return_value=drive), \
             patch.object(cli,"_latest_batch",return_value=("1"*32,"a"*64)):
            result=cli._preflight()
        self.assertEqual(result["status"],"preflight-verified")
        self.assertTrue(result["privateDriveWritable"])
        self.assertFalse(result["imageBackupExecuted"])
        drive.preflight.assert_called_once()
        drive.upload.assert_not_called()

    def test_manual_execute_requires_real_verification_flags(self):
        from unittest.mock import MagicMock
        proof={"status":"independent-encrypted-original-verified",
               "sourcePreserved":True,"deletionAuthorized":False,
               "encryptionVerified":True,"remoteDownloadVerified":True,
               "independentServerVerified":True,"fullBatchRoundTripVerified":True,
               "allReferencesVerified":True}
        with patch.dict(os.environ,_ENV,clear=True), \
             patch.object(cli,"_latest_batch",return_value=("1"*32,"a"*64)), \
             patch.object(cli,"_drive",return_value=MagicMock()), \
             patch("android_image_backup_runner.run_once",return_value=proof) as do:
            result=cli._execute()
        self.assertEqual(result["status"],"verified")
        self.assertTrue(result["remoteDownloadVerified"])
        self.assertFalse(result["deletionAuthorized"])
        self.assertEqual(do.call_count,1)

    def test_failure_output_sanitized(self):
        output=io.StringIO()
        with patch.dict(os.environ,_ENV,clear=True), \
             patch.object(cli,"_execute",side_effect=ValueError(
                 "private image PNG, batch ID and passwords")), \
             contextlib.redirect_stdout(output):
            rc=cli.main(["execute","--acknowledge-one-batch-only"])
        self.assertEqual(rc,3)
        self.assertNotIn("passwords",output.getvalue())
        self.assertNotIn("PNG",output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status"],"failed")


if __name__=="__main__":
    unittest.main()
