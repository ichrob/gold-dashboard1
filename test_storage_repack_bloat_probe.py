"""Strict rollback-only bloat measurement and safe failure tests."""
import json
import os
import unittest
from unittest.mock import patch,Mock

import storage_repack_bloat_probe as probe


class Result:
    def __init__(self,row):self.row=row
    def fetchone(self):return self.row


class FakeConnection:
    def __init__(self,fail_toast=False):
        self.sql=[]
        self.rollback_calls=0
        self.closed=False
        self.fail_toast=fail_toast
    def execute(self,sql,params=None):
        self.sql.append(sql)
        if sql.startswith("SET LOCAL"):return Result(None)
        if "FROM pg_available_extensions" in sql:return Result((None,))
        if "FROM pg_class c" in sql:return Result((777,888,66_838_528))
        if sql.startswith("CREATE EXTENSION"):return Result(None)
        if "pgstattuple_approx" in sql:
            if params==(888,) and self.fail_toast:
                raise ValueError("TOAST scan rejected")
            return Result((1_000_000, 1_000, 50_000, 20.0)
                          if params==(777,) else
                          (52_000_000,100_000,1_000_000,8.2))
        raise AssertionError("Unexpected SQL")
    def rollback(self):self.rollback_calls+=1
    def close(self):self.closed=True


class FakeVerifier:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql):return Result((None,))


class ProbeTests(unittest.TestCase):
    def test_disabled_probe_does_not_connect(self):
        with patch.dict(os.environ,{"BOB_BLOAT_PROBE_ONCE":""}), \
             patch.object(probe,"inspect_once",
                          side_effect=AssertionError("must not run")):
            self.assertIsNone(probe.start_if_enabled())

    def test_transient_extension_is_rolled_back_even_on_success(self):
        source=FakeConnection()
        with patch.object(probe,"_volume_gate",return_value=True), \
             patch("archive_worker.status",return_value={"status":"ready"}), \
             patch.object(probe,"_connect",return_value=source), \
             patch("psycopg.connect",return_value=FakeVerifier()):
            result=probe.inspect_once()
        self.assertEqual(source.rollback_calls,1)
        self.assertTrue(source.closed)
        self.assertEqual(sum("CREATE EXTENSION" in q for q in source.sql),1)
        self.assertTrue(result["rollbackVerified"])
        self.assertFalse(result["extensionLeftInstalled"])
        self.assertEqual(result["mainHeap"]["approxFreeBytes"],50000)
        self.assertEqual(result["toast"]["deadTupleBytes"],100000)
        self.assertEqual(result["combinedDeadAndApproxFreeBytes"],1151000)
        self.assertFalse(result["maintenanceAuthorized"])
        self.assertFalse(result["readyToRepack"])
        self.assertIsNone(result["diskBytesFreed"])
        self.assertNotIn("delete from"," ".join(source.sql).lower())
        self.assertNotIn("vacuum "," ".join(source.sql).lower())

    def test_toast_error_always_rolls_back(self):
        source=FakeConnection(fail_toast=True)
        with patch.object(probe,"_volume_gate",return_value=True), \
             patch("archive_worker.status",return_value={"status":"ready"}), \
             patch.object(probe,"_connect",return_value=source):
            with self.assertRaises(ValueError):
                probe.inspect_once()
        self.assertEqual(source.rollback_calls,1)
        self.assertTrue(source.closed)

    def test_storage_budget_prevents_even_transient_extension(self):
        with patch.object(probe,"_volume_gate",return_value=False), \
             patch("archive_worker.status",return_value={"status":"ready"}), \
             patch.object(probe,"_connect") as sql:
            with self.assertRaises(ValueError):
                probe.inspect_once()
            sql.assert_not_called()

    def test_invalid_results_fail_closed(self):
        class Bad:
            def execute(self,*args):return Result((100,50,80,110))
        with self.assertRaises(ValueError):
            probe._bloat_stats(Bad(),777)

    def test_unauthorized_failure_logs_no_secrets(self):
        import io
        import contextlib
        with patch.dict(os.environ,{"BOB_BLOAT_PROBE_ONCE":"1"}), \
             patch.object(probe,"inspect_once",
                          side_effect=ValueError("password/PRIVATE_DEVICE_ID")), \
             patch("threading.Thread") as thread:
            probe.start_if_enabled()
            callback=thread.call_args.kwargs["target"]
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                callback()
        self.assertIn("probe-unavailable",output.getvalue())
        self.assertNotIn("PRIVATE_DEVICE_ID",output.getvalue())
        self.assertNotIn("password",output.getvalue())
        self.assertIn('"readyToRepack":false',output.getvalue())


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Isolated PostgreSQL 18 CI only")
class TransientPgstattuplePostgresTests(unittest.TestCase):
    def test_extension_is_usable_inside_transaction_but_never_persists(self):
        import psycopg
        dsn=os.environ["BOB_TEST_DATABASE_URL"]
        with psycopg.connect(dsn,autocommit=True) as pre:
            ext=pre.execute("""SELECT installed_version,default_version
                FROM pg_available_extensions WHERE name='pgstattuple'""").fetchone()
        if ext is None:
            self.skipTest("pgstattuple module unavailable in synthetic CI DB")
        was_installed=ext[0] is not None
        c=psycopg.connect(dsn,autocommit=False)
        try:
            c.execute("SET LOCAL statement_timeout='4s'")
            if not was_installed:
                c.execute("CREATE EXTENSION pgstattuple WITH SCHEMA public")
            row=c.execute("""SELECT table_len::bigint,dead_tuple_len::bigint,
                approx_free_space::bigint,scanned_percent::float8
                FROM public.pgstattuple_approx('pg_catalog.pg_class'::regclass)""").fetchone()
            self.assertEqual(len(row),4)
            self.assertGreater(row[0],0)
        finally:
            c.rollback()
            c.close()
        with psycopg.connect(dsn,autocommit=True) as post:
            after=post.execute("""SELECT installed_version
                FROM pg_available_extensions WHERE name='pgstattuple'""").fetchone()
        self.assertEqual(after[0] is not None,was_installed)


if __name__=="__main__":
    unittest.main()
