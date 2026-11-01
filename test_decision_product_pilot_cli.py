"""Manual decision-product pilot CLI never runs without exact user command."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import decision_product_pilot_cli as cli


class ManualPilotCLITests(unittest.TestCase):
    def call(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_default_and_unrecognized_commands_cannot_access_db_or_write(self):
        for args in ([], ["execute"], ["execute", "--extra"],
                     ["status", "secret-token"], ["execute", "--acknowledge-one-row-only", "extra"]):
            with self.subTest(args=args), \
                 patch.object(cli.pilot, "run_once") as run, \
                 patch.object(cli.pilot.codec, "connect") as connect:
                code, message = self.call(args)
                self.assertEqual(code, 2)
                self.assertIn("Usage:", message)
                self.assertNotIn("secret-token", message)
                run.assert_not_called()
                connect.assert_not_called()

    def test_execute_refuses_without_exact_one_use_config(self):
        with patch.object(cli.pilot, "configuration", return_value=None), \
             patch.object(cli.pilot, "run_once") as run, \
             patch.object(cli.pilot.codec, "connect") as connect:
            code, out = self.call(["execute", "--acknowledge-one-row-only"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], "disabled")
        run.assert_not_called()
        connect.assert_not_called()

    def test_execute_one_row_only_and_sanitized_receipt(self):
        private = {"status": "verified-offload", "movedRows": 1,
                   "readThroughVerified": True, "id": "private-attempt",
                   "fileId": "secret-drive-id", "original": {"isin": "PRIVATE"}}
        with patch.object(cli.pilot, "configuration", return_value={"confirmed": True}), \
             patch.object(cli.pilot, "run_once", return_value=private) as run:
            code, out = self.call(["execute", "--acknowledge-one-row-only"])
        self.assertEqual(code, 0)
        run.assert_called_once_with()
        self.assertEqual(json.loads(out), {
            "status": "verified-offload", "movedRows": 1, "diskBytesFreed": None})
        for secret in ("private-attempt", "secret-drive-id", "PRIVATE"):
            self.assertNotIn(secret, out)

    def test_failed_or_deferred_result_is_never_success(self):
        with patch.object(cli.pilot, "configuration", return_value={"confirmed": True}), \
             patch.object(cli.pilot, "run_once",
                          return_value={"status": "deferred-busy", "movedRows": 0}):
            code, out = self.call(["execute", "--acknowledge-one-row-only"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], "deferred-busy")

    def test_bogus_count_and_untrusted_status_fail_closed(self):
        for result in ({"status": "verified-offload", "movedRows": 2},
                       {"status": "verified-offload", "movedRows": True},
                       {"status": "db://secret", "movedRows": 1}):
            with self.subTest(result=result), \
                 patch.object(cli.pilot, "configuration", return_value={"confirmed": True}), \
                 patch.object(cli.pilot, "run_once", return_value=result):
                code, out = self.call(["execute", "--acknowledge-one-row-only"])
            self.assertEqual(code, 3)
            self.assertEqual(json.loads(out)["status"], "failed")
            self.assertNotIn("db://secret", out)

    def test_read_only_preflight_never_claims_or_executes(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        with patch.object(cli.pilot.codec, "connect", return_value=conn), \
             patch.object(cli.pilot, "_preflight",
                          return_value="approved-for-single-row-pilot") as check, \
             patch.object(cli.pilot, "configuration", return_value=None), \
             patch.object(cli.pilot, "run_once") as run, \
             patch.object(cli.pilot, "init") as init:
            code, out = self.call(["preflight"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {
            "status": "approved-for-single-row-pilot",
            "diskBytesFreed": None, "readOnly": True,
            "executionConfigured": False})
        check.assert_called_once()
        run.assert_not_called()
        init.assert_not_called()

    def test_status_does_not_expose_private_ids(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        report = {"status": "no-attempt", "readOnly": True,
                  "secret": "database-password", "fileId": "drive-secret"}
        with patch.object(cli.pilot.codec, "connect", return_value=conn), \
             patch.object(cli.pilot, "status", return_value=report), \
             patch.object(cli.pilot, "run_once") as run:
            code, out = self.call(["status"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "no-attempt")
        self.assertNotIn("database-password", out)
        self.assertNotIn("drive-secret", out)
        run.assert_not_called()

    def test_errors_report_only_exception_class(self):
        with patch.object(cli.pilot, "configuration", return_value={"confirmed": True}), \
             patch.object(cli.pilot, "run_once",
                          side_effect=RuntimeError("secret database URI and product values")):
            code, out = self.call(["execute", "--acknowledge-one-row-only"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out), {
            "status": "failed", "movedRows": 0,
            "diskBytesFreed": None, "errorType": "RuntimeError"})
        self.assertNotIn("secret database", out)


if __name__ == "__main__":
    unittest.main()
