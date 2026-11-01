"""One-shot tail reclamation never repeats, rewrites evidence or leaks secrets."""
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import storage_tail_once as tail
import storage_maintenance as maintenance

SUNDAY = datetime(2026, 11, 1, 9, tzinfo=timezone.utc).timestamp()
MONDAY = datetime(2026, 11, 2, 9, tzinfo=timezone.utc).timestamp()
CONFIG = {"id": "sunday-reclaim-test", "table": "bob_diagnostic_history",
          "confirmed": True}


class FakeConnection:
    autocommit = True

    def __init__(self):
        self.ids = set()
        self.calls = []
        self.next_claim = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def transaction(self):
        return self

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if 'ON CONFLICT(id) DO NOTHING RETURNING id' in sql:
            requested = params[0]
            self.next_claim = requested not in self.ids
            self.ids.add(requested)
        return self

    def fetchone(self):
        return ("claimed",) if self.next_claim else None


class TailSafetyTests(unittest.TestCase):
    def env(self, config=CONFIG):
        return patch.dict(os.environ, {
            "BOB_STORAGE_TAIL_RECLAIM_ONCE": json.dumps(config),
        })

    def test_no_config_or_malformed_config_never_connects(self):
        with patch.dict(os.environ, {"BOB_STORAGE_TAIL_RECLAIM_ONCE": ""}):
            factory = Mock()
            self.assertEqual(tail.run_once(factory=factory)["status"], "disabled")
            factory.assert_not_called()
        for config in ({**CONFIG, "table": "bob_decision_audit"},
                       {**CONFIG, "confirmed": 1},
                       {**CONFIG, "password": "secret"},
                       {**CONFIG, "id": "../unsafe"},
                       {**CONFIG, "confirmed": False}):
            with self.subTest(config=config), self.env(config):
                self.assertIsNone(tail.configuration())

    def test_android_image_tail_is_allowed_but_single_claim_only(self):
        cfg = {"id": "image-prune-vacuum-test",
               "table": "bob_android_list_images", "confirmed": True}
        self.assertIn("bob_android_list_images", maintenance._TABLES)
        answer = {"status": "checked", "tables": [{
            "table": "bob_android_list_images",
            "status": "command-completed",
            "observedRelationBytesDecrease": 65536}]}
        conn = FakeConnection()
        vacuum = Mock(return_value=answer)
        with self.env(cfg), patch.object(tail, "_preflight",
             return_value="approved-for-one-table-vacuum"):
            self.assertEqual(tail.configuration()["table"], "bob_android_list_images")
            first = tail.run_once(factory=lambda:conn,vacuum=vacuum,now=SUNDAY)
            second = tail.run_once(factory=lambda:conn,vacuum=vacuum,now=SUNDAY)
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["observedRelationBytesDecrease"], 65536)
        self.assertIsNone(first["diskBytesFreed"])
        self.assertFalse(first["evidenceDeleted"])
        self.assertEqual(second["status"], "already-claimed")
        vacuum.assert_called_once()
        self.assertTrue(vacuum.call_args.kwargs["reclaim_image_tail"])
        self.assertEqual(vacuum.call_args.kwargs["target_table"],
                         "bob_android_list_images")

    def test_market_hours_fail_before_connection(self):
        with self.env():
            factory = Mock()
            result = tail.run_once(factory=factory, now=MONDAY)
        self.assertEqual(result["status"], "market-hours-deferred")
        factory.assert_not_called()

    def test_stale_proof_never_claims(self):
        conn = FakeConnection()
        with self.env(), patch.object(tail, "_preflight",
                                      return_value="backup-proof-not-fresh"):
            result = tail.run_once(factory=lambda: conn, vacuum=Mock(), now=SUNDAY)
        self.assertEqual(result["status"], "backup-proof-not-fresh")
        self.assertEqual(conn.calls, [])

    def test_once_only_claim_and_single_fixed_target(self):
        conn = FakeConnection()
        result = {"status": "checked", "tables": [{
            "table": "bob_diagnostic_history", "status": "command-completed",
            "observedRelationBytesDecrease": 32768,
        }]}
        vacuum = Mock(return_value=result)
        with self.env(), patch.object(tail, "_preflight",
                                      return_value="approved-for-one-table-vacuum"):
            first = tail.run_once(factory=lambda: conn, vacuum=vacuum, now=SUNDAY)
            second = tail.run_once(factory=lambda: conn, vacuum=vacuum, now=SUNDAY)
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["observedRelationBytesDecrease"], 32768)
        self.assertIsNone(first["diskBytesFreed"])
        self.assertEqual(second["status"], "already-claimed")
        vacuum.assert_called_once()
        self.assertEqual(vacuum.call_args.kwargs["target_table"], "bob_diagnostic_history")
        self.assertTrue(vacuum.call_args.kwargs["reclaim_analysis_tail"])
        self.assertFalse(first["evidenceDeleted"])

    def test_busy_vacuum_is_not_success_and_not_retried(self):
        conn = FakeConnection()
        vacuum = Mock(return_value={"status": "busy", "tables": []})
        with self.env(), patch.object(tail, "_preflight",
                                      return_value="approved-for-one-table-vacuum"):
            first = tail.run_once(factory=lambda:conn,vacuum=vacuum,now=SUNDAY)
            second = tail.run_once(factory=lambda:conn,vacuum=vacuum,now=SUNDAY)
        self.assertEqual(first["status"], "deferred-busy")
        self.assertEqual(second["status"], "already-claimed")
        vacuum.assert_called_once()

    def test_no_spoofed_completion_or_secret_output(self):
        for answer in ({"status":"checked", "tables":[]},
                       {"status":"checked","tables":[{
                           "table":"bob_diagnostic_history",
                           "status":"command-completed",
                           "observedRelationBytesDecrease":True}]},
                       {"status":"checked","tables":[{
                           "table":"bob_decision_audit",
                           "status":"command-completed",
                           "observedRelationBytesDecrease":100}]}):
            conn=FakeConnection()
            with self.subTest(answer=answer), self.env(), patch.object(
                tail,"_preflight",return_value="approved-for-one-table-vacuum"):
                result=tail.run_once(factory=lambda:conn,vacuum=lambda **kw:answer,now=SUNDAY)
            self.assertEqual(result["status"], "deferred")
            self.assertNotIn("fileId",json.dumps(result))
        conn=FakeConnection()
        with self.env(), patch.object(tail,"_preflight",
            return_value="approved-for-one-table-vacuum"):
            result=tail.run_once(factory=lambda:conn,
                vacuum=Mock(side_effect=RuntimeError("secret-password")),now=SUNDAY)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["errorType"],"RuntimeError")
        self.assertNotIn("secret-password",json.dumps(result))

    def test_reject_arbitrary_sql_identifiers_before_opening_connection(self):
        factory=Mock()
        with self.assertRaises(ValueError):
            maintenance.run_once(factory=factory,target_table="bob_decision_audit")
        factory.assert_not_called()

    def test_volume_and_restore_proof_gate(self):
        conn=FakeConnection()
        verified={"latestVerifiedAttempt":{
            "status":"verified","restoreVerified":True,
            "remoteDownloadVerified":True,"evidenceDeleted":False,
            "updatedAt":datetime.fromtimestamp(SUNDAY-1800,timezone.utc).isoformat()}}
        volume={"status":"observed", "resource":tail._RESOURCE,
                "observedAt":SUNDAY-60, "diskUsage":660_000_000,"unit":"bytes"}
        with patch("archive_worker.status",return_value={"status":"ready"}), \
             patch("storage_budget.archive_status",return_value=verified), \
             patch("render_disk_metrics.report",return_value=volume):
            self.assertEqual(tail._preflight(conn,SUNDAY),
                             "approved-for-one-table-vacuum")
        for bad in ({**volume,"diskUsage":900_000_000},
                    {**volume,"observedAt":SUNDAY-400},
                    {**volume,"resource":"another-volume"}):
            with self.subTest(volume=bad), \
                 patch("archive_worker.status",return_value={"status":"ready"}), \
                 patch("storage_budget.archive_status",return_value=verified), \
                 patch("render_disk_metrics.report",return_value=bad):
                self.assertEqual(tail._preflight(conn,SUNDAY),
                                 "fresh-volume-proof-unavailable")
        with patch("archive_worker.status",return_value={"status":"running"}):
            self.assertEqual(tail._preflight(conn,SUNDAY),"archive-running")


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "PostgreSQL CI database required")
class DurableClaimTests(unittest.TestCase):
    def test_one_claim_survives_new_connections(self):
        import psycopg
        import uuid
        dsn=os.environ["BOB_TEST_DATABASE_URL"]
        schema="tail_claim_"+uuid.uuid4().hex
        with psycopg.connect(dsn,autocommit=True) as admin:
            admin.execute("CREATE SCHEMA "+schema)
            try:
                def factory():
                    return psycopg.connect(dsn,autocommit=True,
                        options="-c search_path="+schema)
                answer={"status":"checked","tables":[{
                    "table":"bob_diagnostic_history","status":"command-completed",
                    "observedRelationBytesDecrease":0}]}
                vacuum=Mock(return_value=answer)
                with patch.dict(os.environ,{
                    "BOB_STORAGE_TAIL_RECLAIM_ONCE":json.dumps(CONFIG)}), \
                     patch.object(tail,"_preflight",
                         return_value="approved-for-one-table-vacuum"):
                    first=tail.run_once(factory=factory,vacuum=vacuum,now=SUNDAY)
                    second=tail.run_once(factory=factory,vacuum=vacuum,now=SUNDAY)
                self.assertEqual(first["status"],"completed")
                self.assertEqual(second["status"],"already-claimed")
                self.assertEqual(vacuum.call_count,1)
                with factory() as conn:
                    row=conn.execute("SELECT status,relation_bytes_reduced "
                        "FROM bob_storage_tail_reclaim_attempts").fetchone()
                    self.assertEqual(row,("completed",0))
            finally:
                admin.execute("DROP SCHEMA "+schema+" CASCADE")


if __name__ == "__main__":
    unittest.main()
