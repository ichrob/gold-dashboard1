"""One-table physical reclamation fails closed on missing evidence.

No test invokes pg_repack, changes original Bob tables, or uses real credentials.
"""
import json
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import storage_repack_improvement_once as repack

MONDAY_21=datetime(2026,11,2,21,tzinfo=ZoneInfo("Europe/Zurich")).timestamp()
MONDAY_22=datetime(2026,11,2,22,tzinfo=ZoneInfo("Europe/Zurich")).timestamp()


class ConfigTests(unittest.TestCase):
    def config(self, value):
        return patch.dict(os.environ,{"BOB_IMPROVEMENT_REPACK_ONCE":value})

    def test_only_exact_fixed_target_and_explicit_consent(self):
        good={"id":"once-bob-improvement","target":"bob_improvement_observations",
              "confirmed":True}
        with self.config(json.dumps(good)):
            self.assertEqual(repack.configuration(),good)
        for changes in ({"target":"bob_decision_audit"},
                        {"confirmed":False},{"confirmed":1},
                        {"id":"../untrusted"},{"sql":"DROP TABLE bob_improvement_observations"}):
            with self.subTest(changes=changes),self.config(json.dumps({**good,**changes})):
                self.assertIsNone(repack.configuration())
        with self.config(""):
            self.assertIsNone(repack.configuration())

    def test_quiet_period_excludes_active_trading_session(self):
        self.assertFalse(repack.quiet_period(MONDAY_21))
        self.assertTrue(repack.quiet_period(MONDAY_22))

    def test_disabled_market_hours_and_stale_volume_never_open_connection(self):
        config={"id":"once-bob-improvement","target":"bob_improvement_observations",
                "confirmed":True}
        forbidden=lambda: (_ for _ in ()).throw(AssertionError("must not connect"))
        with self.config(""):
            self.assertEqual(repack.run_once(now=MONDAY_22,connect=forbidden)
                             ["status"],"disabled")
        with self.config(json.dumps(config)):
            self.assertEqual(repack.run_once(now=MONDAY_21,connect=forbidden)
                             ["status"],"market-hours-deferred")
            with patch("archive_worker.status",return_value={"status":"idle"}), \
                 patch.object(repack,"_volume",return_value=None):
                self.assertEqual(repack.run_once(now=MONDAY_22,connect=forbidden)
                                 ["status"],"fresh-volume-proof-unavailable")

    def test_backup_receipt_uses_exact_restore_and_source_scope(self):
        class Conn:
            def __init__(self,proof):self.proof=proof
            def execute(self,*_):return self
            def fetchone(self):return ({"receipt":self.proof},MONDAY_22-100)
        good={"restoreVerified":True,"remoteDownloadVerified":True,
              "scope":"reviewed-evidence-tables-not-full-database-backup",
              "deletionPermitted":False}
        self.assertTrue(repack._backup(Conn(good),MONDAY_22))
        for modification in ({"restoreVerified":False},
                             {"remoteDownloadVerified":False},
                             {"scope":"full-db-assumed"},
                             {"deletionPermitted":True}):
            self.assertFalse(repack._backup(Conn({**good,**modification}),MONDAY_22))

    def test_sensitive_client_connection_only_in_process_environment(self):
        with patch.dict(os.environ,{"DATABASE_URL":
                "postgresql://bobuser:private-secret@db.internal/bob_push_db?sslmode=require"}):
            environment,name=repack._client_environment()
        self.assertEqual(name,"bob_push_db")
        self.assertEqual(environment["PGPASSWORD"],"private-secret")
        self.assertNotIn("private-secret",name)


class RunTests(unittest.TestCase):
    CONFIG={"id":"safe-once","target":"bob_improvement_observations","confirmed":True}
    class Conn:
        autocommit=True
        def __init__(self):
            self.calls=[]
            self.claimed=False
            self.after=False
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def execute(self,sql,params=None):
            self.calls.append((sql,params))
            self.sql=sql
            if "CREATE EXTENSION" in sql:self.after=True
            if "INSERT INTO bob_improvement_repack_attempts" in sql:
                self.pending_claim=not self.claimed
                self.claimed=True
            return self
        def fetchone(self):
            sql=self.sql
            if "pg_try_advisory_lock" in sql:return (True,)
            if "pg_total_relation_size(c.oid)" in sql:return (67_000_000,True)
            if "pg_available_extensions" in sql:return ("1.5.3",)
            if "SELECT count(*)" in sql:return (20_000,)
            if "INSERT INTO bob_improvement_repack_attempts" in sql:
                return ("safe-once",) if self.pending_claim else None
            if "SELECT pg_total_relation_size(%s::regclass)" in sql:
                return (20_000_000,)
            return None

    def _guards(self):
        return [
            patch.dict(os.environ,{"BOB_IMPROVEMENT_REPACK_ONCE":
                                   json.dumps(self.CONFIG)}),
            patch("archive_worker.status",return_value={"status":"idle"}),
            patch.object(repack,"_volume",side_effect=[
                (716_000_000,100),(666_000_000,101)]),
            patch("storage_repack_bloat_probe.inspect_once",
                  return_value={"rollbackVerified":True,
                                "databaseRowsModified":False,
                                "table":"public.bob_improvement_observations",
                                "combinedDeadAndApproxFreeBytes":47_000_000}),
            patch.object(repack,"_wal",
                         return_value={"directoryBytes":48_000_000,
                                       "twoSecondWrittenBytes":100_000}),
            patch.object(repack,"_backup",return_value=True),
            patch.object(repack,"_proof_rows",
                         return_value={("private","1","hashonly")}),
            patch.object(repack,"_client_environment",
                         return_value=({"PGDATABASE":"bob_push_db"},"bob_push_db")),
            patch.object(repack,"_init"),
            patch.object(repack.shutil,"which",return_value="/safe/pg_repack"),
        ]

    def test_repack_is_one_table_no_backend_kills_and_verified(self):
        from contextlib import ExitStack
        c=self.Conn()
        def runner(args,env):
            self.assertIn("--no-kill-backend",args)
            self.assertIn("--no-superuser-check",args)
            self.assertIn("--wait-timeout=3",args)
            self.assertIn("--table=public.bob_improvement_observations",args)
            self.assertNotIn("private-secret",str(args))
            return 0
        with ExitStack() as stack:
            for p in self._guards():stack.enter_context(p)
            result=repack.run_once(now=MONDAY_22,connect=lambda:c,runner=runner)
        self.assertEqual(result["status"],"verified-relation-reduction")
        self.assertEqual(result["observedRelationBytesDecrease"],47_000_000)
        self.assertEqual(result["observedNetVolumeDecreaseBytes"],50_000_000)
        self.assertIsNone(result["diskBytesFreed"])
        self.assertTrue(result["sourceRowsPreserved"])
        sql=" ".join(q for q,_ in c.calls).lower()
        self.assertNotIn("delete from bob_improvement_observations",sql)
        self.assertNotIn("update bob_improvement_observations",sql)
        self.assertNotIn("vacuum full",sql)

    def test_repack_skips_when_insufficient_bloat(self):
        from contextlib import ExitStack
        c=self.Conn()
        with ExitStack() as stack:
            for p in self._guards():stack.enter_context(p)
            with patch("storage_repack_bloat_probe.inspect_once",return_value={
                "rollbackVerified":True,"databaseRowsModified":False,
                "table":"public.bob_improvement_observations",
                "combinedDeadAndApproxFreeBytes":0}):
                result=repack.run_once(now=MONDAY_22,connect=lambda:c)
        self.assertEqual(result["status"],"insufficient-verified-bloat")
        self.assertEqual(c.calls,[])


if __name__=="__main__":
    unittest.main()
