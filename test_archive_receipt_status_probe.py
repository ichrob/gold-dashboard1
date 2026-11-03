"""Archive status can be inspected without credentials or original records."""
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import archive_receipt_status_probe as probe


class Fake:
    def __init__(self,rows):
        self.rows=iter(rows);self.calls=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql):
        self.calls.append(sql)
        return self
    def fetchone(self):return next(self.rows)


class ProbeTests(unittest.TestCase):
    def test_state_extracts_only_safe_receipt_metadata(self):
        now=datetime.now(timezone.utc)
        failed=("failed",now,{"phase":"encrypt-before-upload",
                "errorType":"ValueError",
                "privatePassword":"never-show",
                "receipt":{"driveFileId":"private-id","encryptionVerified":False}})
        verified=("verified",now-timedelta(hours=3),
                  {"receipt":{"restoreVerified":True,"remoteDownloadVerified":True,
                     "encryptionVerified":True,
                     "encryptionVersion":"aes-256-gcm-stream-v1",
                     "driveFileId":"very-private-id","archiveSha256":"f"*64}})
        db=Fake([failed,verified])
        report=probe.inspect_once(factory=lambda:db)
        self.assertEqual(report["status"],"checked")
        self.assertEqual(report["latestAttempt"]["status"],"failed")
        self.assertEqual(report["latestAttempt"]["phase"],"encrypt-before-upload")
        self.assertEqual(report["latestAttempt"]["errorType"],"ValueError")
        self.assertTrue(report["latestVerified"]["encryptionVerified"])
        self.assertFalse(report["latestVerified"]["deletionPermitted"])
        self.assertIsNone(report["diskBytesFreed"])
        private=json.dumps(report)
        self.assertNotIn("never-show",private)
        self.assertNotIn("private-id",private)
        self.assertNotIn("very-private-id",private)
        self.assertNotIn("archiveSha256",private)
        self.assertEqual(len(db.calls),2)
        self.assertTrue(all(sql.lstrip().startswith("SELECT") for sql in db.calls))

    def test_untrusted_fields_do_not_escape(self):
        now=datetime.now(timezone.utc)
        dangerous=("internal-state",now,
                 {"phase":"password=secret","errorType":"Error;token=secret",
                  "receipt":{"encryptionVersion":"mysecret","restoreVerified":"true"}})
        report=probe._redacted(dangerous)
        self.assertEqual(report["status"],"unknown")
        self.assertIsNone(report["phase"])
        self.assertIsNone(report["errorType"])
        self.assertIsNone(report["encryptionVersion"])
        self.assertFalse(report["restoreVerified"])
        self.assertNotIn("secret",str(report))

    def test_disabled_has_no_database_or_worker_access(self):
        with patch.dict(os.environ,{"BOB_ARCHIVE_STATUS_PROBE_ONCE":"0"}), \
             patch("threading.Thread") as thread:
            probe.start_if_enabled()
            thread.assert_not_called()

    def test_failure_does_not_log_private_exception_message(self):
        def fail():
            raise RuntimeError("private database password")
        with patch.dict(os.environ,{"BOB_ARCHIVE_STATUS_PROBE_ONCE":"1",
                                    "DATABASE_URL":"test-only"}), \
             patch.object(probe,"inspect_once",side_effect=fail), \
             patch("threading.Thread") as thread:
            old=probe._THREAD
            probe._THREAD=None
            try:
                probe.start_if_enabled()
                work=thread.call_args.kwargs["target"]
                with patch("time.sleep"), redirect_stdout(io.StringIO()) as captured:
                    work()
                result=captured.getvalue()
                self.assertIn("BOB_ARCHIVE_RECEIPT_STATUS",result)
                self.assertNotIn("private database password",result)
            finally:
                probe._THREAD=old


if __name__=="__main__":
    unittest.main()
