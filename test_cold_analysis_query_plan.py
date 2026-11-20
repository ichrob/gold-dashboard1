"""Regression tests: operator-only EXPLAIN, no SELECT execution or secret leaks."""
from contextlib import nullcontext
import inspect as pyinspect
import json
import os
import re
import unittest
import uuid

import cold_analysis
import cold_metrics
import cold_analysis_query_plan as target


def sample_plan():
    return [{"Plan": {
        "Node Type": "Limit", "Plan Rows": 500, "Total Cost": 170.2,
        "Plans": [{"Node Type": "Index Scan",
                   "Index Name": "bob_diagnostic_history_stage",
                   "Relation Name": "bob_diagnostic_history",
                   "Index Cond": "(stage = 'PRIVATE')",
                   "Filter": "SECRET_SHOULD_NOT_LEAK",
                   "Plan Rows": 1000, "Total Cost": 890.4}]} }]


class FakeConn:
    def __init__(self, mode="on", data=None, error=None):
        self.mode = mode
        self.data = sample_plan() if data is None else data
        self.error = error
        self.statements = []
        self.params = []
    def transaction(self):
        return nullcontext()
    def execute(self, sql, params=None):
        self.statements.append(sql)
        self.params.append(params)
        if self.error is not None:
            raise self.error
        if sql == "SHOW transaction_read_only":
            return self
        if sql.startswith("EXPLAIN "):
            return self
        if sql.startswith("SET LOCAL "):
            return self
        raise AssertionError("Unexpected DB operation")
    def fetchone(self):
        if self.statements[-1] == "SHOW transaction_read_only":
            return (self.mode,)
        return (self.data,)


class ColdAnalysisPlanTests(unittest.TestCase):
    def test_exact_sql_and_parameter_contract_matches_live_worker(self):
        worker = pyinspect.getsource(cold_analysis.offload_batch)
        match = re.search(r"conn.execute\('''(SELECT id,stage,observed_at,build,payload"
                          r" FROM bob_diagnostic_history.*?)'''", worker, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(" ".join(target._CANDIDATES.split()), " ".join(match.group(1).split()))
        self.assertEqual(target._TAG, cold_analysis.TAG)
        self.assertEqual(target._LIMIT, cold_metrics.MAX_ROWS)
        self.assertIn("EXPLAIN (FORMAT JSON, COSTS TRUE)", target._EXPLAIN)
        self.assertNotIn("ANALYZE", target._EXPLAIN)

    def test_readonly_plan_projection_never_exposes_sql_filter_or_payload(self):
        conn = FakeConn()
        report = target.inspect(conn)
        self.assertEqual(report["status"], "estimated-plan-observed")
        self.assertEqual([item["node"] for item in report["nodes"]], ["Limit", "Index Scan"])
        self.assertEqual(report["nodes"][1]["index"], "bob_diagnostic_history_stage")
        self.assertTrue(report["nodes"][1]["hasFilter"])
        self.assertTrue(report["nodes"][1]["hasIndexCondition"])
        self.assertEqual(report["nodes"][0]["estimatedRows"], 500)
        self.assertEqual(conn.params[-1], ("_bobColdAnalysisV1", 500))
        self.assertEqual(len(conn.statements), 4)
        self.assertTrue(all(x.startswith(("SHOW", "SET LOCAL", "EXPLAIN")) for x in conn.statements))
        self.assertFalse(report["queryExecuted"])
        self.assertFalse(report["sourceRowsModified"])
        self.assertFalse(report["maintenanceAuthorized"])
        self.assertNotIn("SECRET_SHOULD_NOT_LEAK", json.dumps(report))
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertNotIn("SELECT id,", json.dumps(report))

    def test_write_transaction_is_rejected_before_running_explain(self):
        conn = FakeConn(mode="off")
        report = target.inspect(conn)
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["reason"], "read-only-transaction-required")
        self.assertEqual(conn.statements, ["SHOW transaction_read_only"])

    def test_errors_are_redacted_and_fail_closed(self):
        conn = FakeConn(error=RuntimeError("secret-Bob-DB-token"))
        report = target.inspect(conn)
        self.assertEqual(report["status"], "unavailable")
        self.assertNotIn("secret-Bob", json.dumps(report))
        self.assertEqual(target._project(None)["status"], "unavailable")
        self.assertEqual(target._project([{"Plan": {"Node Type": "bogus",
            "Total Cost": 1, "Plan Rows": 1}}])["status"], "unavailable")
        unsafe = [{"Plan": {"Node Type": "Seq Scan", "Plan Rows": -1, "Total Cost": 1,
                            "Filter": "password=STAY_PRIVATE"}}]
        self.assertEqual(target._project(unsafe)["status"], "unavailable")
        self.assertNotIn("STAY_PRIVATE", json.dumps(target._project(unsafe)))

    def test_unknown_index_name_is_masked(self):
        raw = sample_plan()
        raw[0]["Plan"]["Plans"][0]["Index Name"] = "private-index"
        report = target._project(raw)
        self.assertEqual(report["nodes"][1]["index"], "other-or-unreported")
        self.assertNotIn("private-index", json.dumps(report))

    def test_operator_only_cli_rejects_accidental_run(self):
        self.assertEqual(target.main([]), 2)
        self.assertEqual(target.main(["--help"]), 2)


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Requires isolated CI Postgres database")
class IsolatedPlanTests(unittest.TestCase):
    def test_explain_is_safe_and_leaves_test_rows_unchanged(self):
        import psycopg
        from psycopg import sql
        schema = "cold_analysis_plan_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                admin.execute(sql.SQL("""CREATE TABLE {}.bob_diagnostic_history (
                    id TEXT PRIMARY KEY, stage TEXT, observed_at DOUBLE PRECISION,
                    build TEXT, recorded_at TIMESTAMPTZ, payload JSONB
                    )""").format(sql.Identifier(schema)))
                admin.execute(sql.SQL("""INSERT INTO {}.bob_diagnostic_history
                    VALUES ('case-1','analysis',123.0,NULL,now()-interval '8 hours',
                            'null'::jsonb)""").format(sql.Identifier(schema)))
                with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                        options="-c default_transaction_read_only=on") as reader:
                    reader.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                    report = target.inspect(reader)
                    self.assertEqual(report["status"], "estimated-plan-observed")
                    self.assertTrue(report["nodes"])
                    self.assertFalse(report["queryExecuted"])
                    self.assertEqual(reader.execute("SHOW transaction_read_only").fetchone()[0], "on")
                count = admin.execute(sql.SQL("SELECT count(*) FROM {}.bob_diagnostic_history")
                                       .format(sql.Identifier(schema))).fetchone()[0]
                self.assertEqual(count, 1)
            finally:
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
