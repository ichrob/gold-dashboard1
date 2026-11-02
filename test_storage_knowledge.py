"""Regression tests for bounded non-destructive five-area knowledge snapshots."""
import json
import os
import unittest
import uuid
from contextlib import nullcontext
from unittest.mock import patch

import storage_knowledge as k


class FoldTests(unittest.TestCase):
    def test_all_five_areas_are_descriptive_only_and_redacted(self):
        examples = {
            "diagnoses": [("secret-trace", "analysis-failed", "failed")],
            "decisions": [("secret-decision", "LONG", "true")],
            "improvements": [("private-campaign", "observation", "verified")],
            "simulations": [("private-trade", "normal1000oct", "inconclusive")],
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
        summary = k.fold("simulations", [("ref", "risk2000", original)])
        self.assertEqual(summary["outcomes"], {"unclassified": 1})
        self.assertNotIn(original, json.dumps(summary))
        self.assertNotIn("profit", json.dumps(summary).lower())

    def test_observed_or_per_metric_only_not_misreported_as_pass(self):
        s = k.fold("quality", [
            ("check-1", "metric", "observed"),
            ("check-2", "metric", "individual-metrics-no-overall-status"),
            ("check-3", "metric", "archived-original-not-inline"),
        ])
        self.assertEqual(s["outcomes"]["observed"], 1)
        self.assertEqual(s["outcomes"]["individual-metrics-no-overall-status"], 1)
        self.assertEqual(s["outcomes"]["archived-original-not-inline"], 1)
        self.assertNotIn("matched", s["outcomes"])
        self.assertFalse(s["deletionAuthorized"])

    def test_repeated_ids_unbounded_rows_and_bad_areas_fail(self):
        with self.assertRaises(ValueError):
            k.fold("diagnoses", [("same", "input", "ok")] * 2)
        with self.assertRaises(ValueError):
            k.fold("diagnoses", [("x"+str(i), "input", "ok")
                                  for i in range(k.SAMPLE_CAP+1)])
        with self.assertRaises(ValueError):
            k.fold("unknown", [])
        self.assertEqual(k.fold("quality", [])["status"], "observed-empty")


class SimulationSourcesTests(unittest.TestCase):
    def test_full_per_ledger_page_never_claims_complete_history(self):
        class Fake:
            def __init__(self): self.number = 0
            def execute(self, sql, params=()):
                self.number += 1
                self.last = (sql, params)
                return self
            def fetchall(self):
                if self.number == 1:
                    return [("c"+str(i), "legacy", "closed") for i in range(7)]
                return []
        rows, coverage = k.sample_simulations(Fake())
        self.assertEqual(len(rows), 7)
        self.assertTrue(coverage["moreSourceRowsMayExist"])
        self.assertFalse(coverage["netReturnVerified"])

    def test_full_risk_page_marks_potential_older_cases(self):
        class Fake:
            def __init__(self): self.number = 0
            def execute(self, sql, params=()):
                self.number += 1
                return self
            def fetchall(self):
                if self.number == 9:
                    return [("risk-"+str(i), "risk2000", "closed") for i in range(8)]
                return []
        rows, coverage = k.sample_simulations(Fake())
        self.assertEqual(len(rows), 8)
        self.assertTrue(coverage["moreSourceRowsMayExist"])
        self.assertFalse(coverage["strategyWinnerConfirmed"])

    def test_all_isolated_accounts_are_read_not_merged(self):
        import paper_portfolios
        self.assertEqual(set(k._PROFILE_NAMES), set(paper_portfolios.POLICIES))
        self.assertEqual(8 * k._SIM_PER_LEDGER + k._RISK_SAMPLE, k.SAMPLE_CAP)
        class Fake:
            def __init__(self):
                self.tables = []
            def execute(self, sql, params=()):
                self.tables.append(sql)
                return self
            def fetchall(self):
                return []
        fake = Fake()
        rows, coverage = k.sample_simulations(fake)
        self.assertEqual(rows, [])
        self.assertEqual(coverage["ledgersInspected"], 9)
        self.assertFalse(coverage["moreSourceRowsMayExist"])
        self.assertEqual(len(fake.tables), 9)
        self.assertIn("bob_paper_normal1000oct_cases", " ".join(fake.tables))
        self.assertIn("bob_risk_paper_cases", " ".join(fake.tables))
        self.assertFalse(coverage["strategyWinnerConfirmed"])


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
                        "improvements": "observation", "simulations": "legacy",
                        "quality": "metric",
                    }[area], {
                        "diagnoses": "ok", "decisions": "false",
                        "improvements": "pending", "simulations": "pending",
                        "quality": "matched",
                    }[area])]
                elif "FROM bob_paper_" in sql or "FROM bob_risk_paper_cases" in sql:
                    self.rows = []
                return self
            if "INSERT INTO bob_knowledge_snapshots" in sql:
                self.writes.append(params)
            return self
        def fetchall(self):
            return self.rows

    def test_captures_five_small_safe_summaries_no_deletion(self):
        c = self.Conn()
        with patch.object(k, "sample_simulations", return_value=(
                [("simulations-private", "legacy", "pending")],
                {"ledgersInspected": 9})): 
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
        with patch.object(k, "sample_simulations", return_value=(
                [("simulations-private", "legacy", "pending")],
                {"ledgersInspected": 9})): 
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
                import paper_portfolios
                for name in paper_portfolios.POLICIES:
                    table = paper_portfolios.names(name)["bob_paper_cases"]
                    conn.execute("""CREATE TABLE """ + table + """ (
                        id TEXT PRIMARY KEY,day TEXT,started_at TIMESTAMPTZ,
                        closed_at TIMESTAMPTZ,payload JSONB)""")
                conn.execute("""CREATE TABLE bob_risk_paper_cases (
                    id TEXT PRIMARY KEY,payload JSONB)""")
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
                conn.execute("""INSERT INTO bob_metric_checks
                    VALUES('v2','15m',2,1793645640001,
                           '{"_bobColdMetricV2":["internal-example",0]}')""")
                conn.execute("""INSERT INTO bob_metric_checks
                    VALUES('v3','product:example',3,1793645640002,
                           '{"metrics":{"adx":{"status":"matched"}},"status":"observed"}')""")
                conn.execute("""INSERT INTO bob_metric_checks
                    VALUES('v4','trade:example',4,1793645640003,
                           '{"metrics":{"pnl":{"status":"mismatch"}}}')""")
                conn.execute("""INSERT INTO bob_paper_normal1000oct_cases
                    VALUES('profile-1','2026-11-02',now(),now(),
                           '{"status":"inconclusive"}')""")
                conn.execute("""INSERT INTO bob_risk_paper_cases
                    VALUES('risk-1','{"status":"closed"}')""")
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
                sim = report["areas"]["simulations"]
                self.assertEqual(sim["simulationCoverage"]["ledgersInspected"], 9)
                self.assertEqual(sim["simulationCoverage"]["sampledPerLedger"]["normal1000oct"], 1)
                self.assertFalse(sim["simulationCoverage"]["moreSourceRowsMayExist"])
                self.assertFalse(sim["moreSourceRowsMayExist"])
                self.assertEqual(sim["simulationCoverage"]["sampledPerLedger"]["risk2000"], 1)
                self.assertEqual(sim["outcomes"]["inconclusive"], 1)
                self.assertFalse(sim["simulationCoverage"]["netReturnVerified"])
                self.assertFalse(sim["simulationCoverage"]["strategyWinnerConfirmed"])
                self.assertEqual(report["areas"]["quality"]["outcomes"]["archived-original-not-inline"], 1)
                self.assertEqual(report["areas"]["quality"]["outcomes"]["observed"], 1)
                self.assertEqual(report["areas"]["quality"]["outcomes"]["individual-metrics-no-overall-status"], 1)
                self.assertEqual(report["areas"]["quality"]["outcomes"]["matched"], 1)
                # A source's metric subfield is not a verified overall verdict.
                self.assertEqual(report["areas"]["quality"]["sampledRows"], 4)
                self.assertFalse(report["deletionAuthorized"])
                conn.execute("ROLLBACK")
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
