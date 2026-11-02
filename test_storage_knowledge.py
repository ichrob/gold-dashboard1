"""Regression tests for bounded non-destructive five-area knowledge snapshots."""
import json
import os
import unittest
import uuid
from contextlib import nullcontext

import storage_knowledge as k


class FoldTests(unittest.TestCase):
    def test_all_five_areas_are_descriptive_only_and_redacted(self):
        examples = {
            "diagnoses": [("secret-trace", "analysis-failed", "failed")],
            "decisions": [("secret-decision", "LONG", "true")],
            "improvements": [("private-campaign", "observation", "verified")],
            "simulations": [("private-trade", "closed", "completed")],
            "quality": [("private-metric", "metric", "mismatch")],
        }
        for area, rows in examples.items():
            with self.subTest(area=area):
                summary = k.fold(area, rows)
                encoded = json.dumps(summary)
                self.assertEqual(summary["sampledRows"], 1)
                self.assertFalse(summary["deletionAuthorized"])
                self.assertFalse(summary["archiveVerifiedForThisWindow"])
                self.assertIsNone(summary["physicalBytesFreed"])
                self.assertIn("not-validated-learning", summary["interpretationStatus"])
                self.assertNotIn(rows[0][0], encoded)
                self.assertEqual(len(summary["sourceKeyFingerprint"]), 64)

    def test_unknown_labels_never_leak_and_no_false_profit(self):
        original = "possibly-sensitive-token"
        summary = k.fold("simulations", [("ref", "closed", original)])
        self.assertEqual(summary["outcomes"], {"unclassified": 1})
        self.assertNotIn(original, json.dumps(summary))
        self.assertNotIn("profit", json.dumps(summary).lower())

    def test_repeated_ids_unbounded_rows_and_bad_areas_fail(self):
        with self.assertRaises(ValueError):
            k.fold("diagnoses", [("same", "input", "ok")] * 2)
        with self.assertRaises(ValueError):
            k.fold("diagnoses", [("x"+str(i), "input", "ok")
                                  for i in range(k.SAMPLE_CAP+1)])
        with self.assertRaises(ValueError):
            k.fold("unknown", [])
        self.assertEqual(k.fold("quality", [])["status"], "observed-empty")


class CaptureTests(unittest.TestCase):
    class Conn:
        def __init__(self, bad=None):
            self.bad = bad
            self.writes = []
        def transaction(self):
            return nullcontext()
        def execute(self, sql, params=None):
            self.last = sql
            if sql.startswith("SELECT"):
                area = next((a for a in k.AREAS
                             if "FROM " + {
                                 "diagnoses": "bob_diagnostic_history",
                                 "decisions": "bob_decision_audit",
                                 "improvements": "bob_improvement_observations",
                                 "simulations": "bob_paper_cases",
                                 "quality": "bob_metric_checks",
                             }[a] in sql), None)
                if area == self.bad:
                    raise TimeoutError("private DB data")
                if area:
                    self.rows = [(area + "-private", {
                        "diagnoses": "input", "decisions": "SHORT",
                        "improvements": "observation", "simulations": "open",
                        "quality": "metric",
                    }[area], {
                        "diagnoses": "ok", "decisions": "false",
                        "improvements": "pending", "simulations": "pending",
                        "quality": "matched",
                    }[area])]
                return self
            if "INSERT INTO bob_knowledge_snapshots" in sql:
                self.writes.append(params)
            return self
        def fetchall(self):
            return self.rows

    def test_captures_five_small_safe_summaries_no_deletion(self):
        c = self.Conn()
        result = k.capture(c, 1793645640)
        self.assertEqual(set(result), set(k.AREAS))
        self.assertEqual(len(c.writes), 5)
        for area, slot, payload in c.writes:
            self.assertEqual(area, json.loads(payload)["area"])
            self.assertEqual(slot, 1793645640//86400*86400)
            self.assertNotIn("private", payload)
            self.assertFalse(json.loads(payload)["deletionAuthorized"])

    def test_one_failing_area_does_not_mark_others_successful_or_delete(self):
        c = self.Conn(bad="improvements")
        result = k.capture(c, 1793645640)
        self.assertEqual(result["improvements"], "not-observed")
        self.assertEqual(len(c.writes), 4)


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "CI PostgreSQL integration")
class PostgresKnowledgeTests(unittest.TestCase):
    def test_all_five_sources_preserved_after_snapshot_and_read(self):
        import psycopg
        from psycopg import sql
        schema = "knowledge_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                conn.execute("""CREATE TABLE bob_diagnostic_history (
                    id TEXT PRIMARY KEY,stage TEXT,payload JSONB,
                    recorded_at TIMESTAMPTZ DEFAULT now())""")
                conn.execute("""CREATE TABLE bob_decision_audit (
                    id TEXT PRIMARY KEY,payload JSONB,
                    recorded_at TIMESTAMPTZ DEFAULT now())""")
                conn.execute("""CREATE TABLE bob_improvement_observations (
                    campaign TEXT,slot BIGINT,payload JSONB,
                    PRIMARY KEY(campaign,slot))""")
                conn.execute("""CREATE TABLE bob_paper_cases (
                    id TEXT PRIMARY KEY,day TEXT,started_at TIMESTAMPTZ,
                    closed_at TIMESTAMPTZ,payload JSONB)""")
                conn.execute("""CREATE TABLE bob_metric_checks (
                    version TEXT,scope TEXT,bar_at BIGINT,checked_at BIGINT,
                    payload JSONB,PRIMARY KEY(version,scope,bar_at))""")
                k.init(conn)
                conn.execute("""INSERT INTO bob_diagnostic_history(id,stage,payload)
                    VALUES('d1','input','{"outcome":"ok"}')""")
                conn.execute("""INSERT INTO bob_decision_audit(id,payload)
                    VALUES('a1','{"direction":"LONG","marketEvaluable":true}')""")
                conn.execute("""INSERT INTO bob_improvement_observations
                    VALUES('example',1,'{"status":"pending"}')""")
                conn.execute("""INSERT INTO bob_paper_cases
                    VALUES('p1','2026-11-02',now(),NULL,'{"status":"pending"}')""")
                conn.execute("""INSERT INTO bob_metric_checks
                    VALUES('v1','15m',1,1793645640000,'{"status":"matched"}')""")
                original = [conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                    for table in ("bob_diagnostic_history", "bob_decision_audit",
                                  "bob_improvement_observations", "bob_paper_cases",
                                  "bob_metric_checks")]
                statuses = k.capture(conn, 1793645640)
                self.assertEqual(set(statuses.values()), {"sampled"})
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM bob_knowledge_snapshots").fetchone()[0], 5)
                self.assertEqual(original, [conn.execute(
                    "SELECT count(*) FROM " + table).fetchone()[0]
                    for table in ("bob_diagnostic_history", "bob_decision_audit",
                                  "bob_improvement_observations", "bob_paper_cases",
                                  "bob_metric_checks")])
                conn.execute("BEGIN READ ONLY")
                report = k.report(conn)
                self.assertEqual(report["status"], "observed")
                self.assertEqual(set(report["areas"]), set(k.AREAS))
                self.assertFalse(report["deletionAuthorized"])
                conn.execute("ROLLBACK")
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
