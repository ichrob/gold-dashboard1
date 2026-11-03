"""One-decision rollback safety and isolated PostgreSQL proof."""
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import cold_decision_products as reader
import cold_decision_product_writer as writer
import decision_product_single_rollback as rollback
from test_cold_decision_product_writer import FakePrivateDrive


class RollbackConfigurationTests(unittest.TestCase):
    def test_disabled_by_default_without_db_or_remote_access(self):
        conn = MagicMock()
        with patch.dict(os.environ, {"BOB_DECISION_PRODUCT_ROLLBACK_ENABLED": "0"}):
            result = rollback.restore_one(conn, "old-decision", approval={
                "confirmed": True, "observedAt": 1000}, now=1000)
        self.assertEqual(result["status"], "disabled")
        conn.execute.assert_not_called()

    def test_stale_or_missing_operator_approval_is_blocked(self):
        conn = MagicMock()
        with patch.dict(os.environ, {"BOB_DECISION_PRODUCT_ROLLBACK_ENABLED": "1"}):
            for approval in (None, {}, {"confirmed": False, "observedAt": 1000},
                             {"confirmed": True, "observedAt": 0},
                             {"confirmed": True, "observedAt": 1000, "extra": True}):
                self.assertEqual(rollback.restore_one(
                    conn, "old-decision", approval=approval, now=2000)["status"],
                    "disabled")
        conn.execute.assert_not_called()


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Isolated PostgreSQL CI fixture")
class PostgreSQLSingleDecisionRollbackTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.types.json import Jsonb
        self.conn = psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                                    autocommit=True)
        self.schema = "decision_rollback_" + uuid.uuid4().hex
        self.conn.execute("CREATE SCHEMA " + self.schema)
        self.conn.execute("SET search_path TO " + self.schema)
        self.conn.execute("""CREATE TABLE bob_decision_audit
            (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL,
             payload JSONB NOT NULL)""")
        self.conn.execute("CREATE INDEX decision_rollback_time ON "
                          "bob_decision_audit(recorded_at,id)")
        writer.init(self.conn)
        self.now = 1780000000.0
        self.at = datetime.fromtimestamp(self.now, tz=timezone.utc)-timedelta(days=22)
        self.products = [
            {"isin": "TEST-" + str(i), "quote": 9007199254740993,
             "quoteAt": "2026-05-01T10:00:00Z"} for i in range(12)]
        self.original = {
            "direction": "WAIT", "recordedAt": 1779000000000,
            "marketEvaluable": False, "products": self.products,
            "origin": "comparison-only"}
        self.conn.execute(
            "INSERT INTO bob_decision_audit (id,recorded_at,payload) "
            "VALUES (%s,%s,%s)", ("decision-rollback-1", self.at, Jsonb(self.original)))
        self.drive = FakePrivateDrive()
        with patch.dict(os.environ, {"BOB_COLD_DECISION_PRODUCTS_ENABLED": "1"}):
            result = writer.offload_batch(self.conn,self.drive,approval={
                "restoreVerified": True, "remoteDownloadVerified": True,
                "observedAt": self.now},now=self.now,max_updates=1)
        self.assertEqual(result["movedRows"],1)
        self.pointer = self.conn.execute(
            "SELECT payload FROM bob_decision_audit WHERE id=%s",
            ("decision-rollback-1",)).fetchone()[0]
        self.assertIn(reader.TAG,self.pointer)

    def tearDown(self):
        self.conn.execute("RESET search_path")
        self.conn.execute("DROP SCHEMA " + self.schema + " CASCADE")
        self.conn.close()

    def _restore(self):
        with patch.dict(os.environ, {"BOB_DECISION_PRODUCT_ROLLBACK_ENABLED": "1"}):
            return rollback.restore_one(
                self.conn,"decision-rollback-1",drive=self.drive,
                approval={"confirmed":True,"observedAt":self.now},now=self.now)

    def test_verified_original_inline_is_restored_atomically(self):
        outcome=self._restore()
        self.assertEqual(outcome["status"],"restored-original-inline")
        self.assertEqual(outcome["restoredRows"],1)
        self.assertIsNone(outcome["diskBytesFreed"])
        self.assertEqual(outcome["archiveObjectsDeleted"],0)
        recovered=self.conn.execute(
            "SELECT recorded_at,payload FROM bob_decision_audit WHERE id=%s",
            ("decision-rollback-1",)).fetchone()
        self.assertEqual(recovered[0],self.at)
        self.assertEqual(recovered[1],self.original)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM bob_cold_decision_product_refs").fetchone()[0],0)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM bob_cold_decision_product_objects").fetchone()[0],1)
        self.assertEqual(self._restore()["status"],"not-a-pointer")

    def test_corrupted_remote_chunk_never_changes_pointer(self):
        self.drive.corrupt=True
        result=self._restore()
        self.assertEqual(result["status"],"original-unavailable")
        saved=self.conn.execute(
            "SELECT payload FROM bob_decision_audit WHERE id=%s",
            ("decision-rollback-1",)).fetchone()[0]
        self.assertEqual(saved,self.pointer)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM bob_cold_decision_product_refs").fetchone()[0],1)
