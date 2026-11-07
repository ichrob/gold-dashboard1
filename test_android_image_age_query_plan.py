"""Synthetic and isolated-CI checks for the separate image-age EXPLAIN only."""
from contextlib import nullcontext
import json
import os
import unittest
import uuid

import android_image_age_review as age
import android_image_age_query_plan as target


def example_plan():
    return [{"Plan": {"Node Type": "Limit", "Plan Rows": 24,
                      "Total Cost": 300.0, "Plans": [{
        "Node Type": "Seq Scan", "Plan Rows": 400,
        "Total Cost": 200.0, "Filter": "PRIVATE_IMAGE_CONTENT_SHOULD_NOT_LEAK",
        "Relation Name": "bob_android_list_images"}]}}]


class FakeConnection:
    def __init__(self, mode="on", plan=None, error=None):
        self.mode = mode
        self.plan = example_plan() if plan is None else plan
        self.error = error
        self.queries = []
        self.parameters = []
    def transaction(self):
        return nullcontext()
    def execute(self, query, params=None):
        self.queries.append(query)
        self.parameters.append(params)
        if self.error is not None:
            raise self.error
        if query == "SHOW transaction_read_only" or query.startswith(
                ("SET LOCAL ", "EXPLAIN ")):
            return self
        raise AssertionError("Unexpected query")
    def fetchone(self):
        return (self.mode,) if self.queries[-1] == "SHOW transaction_read_only" else (self.plan,)


class ImageAgeQueryPlanTests(unittest.TestCase):
    def test_exact_other_sql_not_cold_analysis_or_runtime_query(self):
        self.assertEqual(target._EXPLAIN, "EXPLAIN (FORMAT JSON, COSTS TRUE) " + age._SQL)
        self.assertEqual(target._LIMIT, age._SAMPLE)
        self.assertIn("bob_android_list_images", target._EXPLAIN)
        self.assertIn("jsonb_path_exists", target._EXPLAIN)
        self.assertNotIn("bob_diagnostic_history", target._EXPLAIN)
        self.assertNotIn("ANALYZE", target._EXPLAIN)
        self.assertEqual(target.main([]), 2)

    def test_only_plan_is_requested_and_redacted(self):
        conn = FakeConnection()
        outcome = target.inspect(conn)
        self.assertEqual(outcome["status"], "estimated-plan-observed")
        self.assertEqual([item["node"] for item in outcome["nodes"]],
                         ["Limit", "Seq Scan"])
        self.assertTrue(outcome["nodes"][1]["hasFilter"])
        self.assertEqual(conn.queries, [
            "SHOW transaction_read_only",
            "SET LOCAL statement_timeout='750ms'",
            "SET LOCAL lock_timeout='200ms'",
            target._EXPLAIN])
        self.assertEqual(conn.parameters[-1], (24,))
        self.assertFalse(outcome["queryExecuted"])
        self.assertFalse(outcome["oldImageDeletionAuthorized"])
        self.assertFalse(outcome["sourceRowsModified"])
        self.assertIsNone(outcome["physicalBytesFreed"])
        self.assertNotIn("PRIVATE_IMAGE_CONTENT_SHOULD_NOT_LEAK", json.dumps(outcome))
        self.assertNotIn("SELECT i.created_at", json.dumps(outcome))
        self.assertNotIn("batch_id", json.dumps(outcome))

    def test_write_transaction_fails_before_plan(self):
        conn = FakeConnection(mode="off")
        result = target.inspect(conn)
        self.assertEqual(result["reason"], "read-only-transaction-required")
        self.assertEqual(conn.queries, ["SHOW transaction_read_only"])

    def test_unknown_nodes_and_indices_cannot_disclose_private_names(self):
        invalid = [{"Plan": {"Node Type": "Unknown", "Plan Rows": 1,
                             "Total Cost": 1, "Filter": "SECRET"}}]
        self.assertEqual(target._project(invalid)["status"], "unavailable")
        with_index = [{"Plan": {"Node Type": "Index Scan",
                                "Index Name": "user_private_name",
                                "Index Cond": "private-user-id", "Plan Rows": 1,
                                "Total Cost": 3}}]
        report = target._project(with_index)
        self.assertEqual(report["nodes"][0]["index"], "other-or-unreported")
        self.assertNotIn("user_private_name", json.dumps(report))
        self.assertNotIn("private-user-id", json.dumps(report))

    def test_exceptions_redacted_and_output_bounded(self):
        conn = FakeConnection(error=RuntimeError("SUPERSECRET_DSN"))
        self.assertNotIn("SUPERSECRET", json.dumps(target.inspect(conn)))
        self.assertEqual(target._project(None)["status"], "unavailable")
        deep = {"Node Type": "Seq Scan", "Plan Rows": 1, "Total Cost": 1}
        head = {"Node Type": "Append", "Plan Rows": 1, "Total Cost": 1,
                "Plans": [dict(deep) for _ in range(12)]}
        result = target._project([{"Plan": head}])
        self.assertEqual(result["status"], "estimated-plan-observed")
        self.assertEqual(len(result["nodes"]), 12)
        self.assertTrue(result["nodeListTruncated"])
        head["Plans"].append(dict(deep))
        self.assertEqual(target._project([{"Plan": head}])["status"], "unavailable")


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "PostgreSQL CI fixture only; never production")
class IsolatedPostgresPlanTests(unittest.TestCase):
    def test_explain_does_not_read_png_or_change_rows(self):
        import psycopg
        from psycopg import sql
        schema = "image_age_explain_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"], autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                admin.execute(sql.SQL("""CREATE TABLE {}.bob_android_list_images (
                    batch_id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL,
                    import_receipt JSONB, parsed_items JSONB,
                    processing_at TIMESTAMPTZ, payload JSONB NOT NULL)""").format(
                        sql.Identifier(schema)))
                admin.execute(sql.SQL("""INSERT INTO {}.bob_android_list_images
                    VALUES ('private-case',now()-interval '3 days',
                    '{"stage":"synced"}',NULL,NULL,
                    '{"images":[{"png":"DO_NOT_RETURN_OR_EXTRACT"}]}')""").format(
                        sql.Identifier(schema)))
                with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                        options="-c default_transaction_read_only=on") as reader:
                    reader.execute(sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(schema)))
                    result = target.inspect(reader)
                    self.assertEqual(result["status"], "estimated-plan-observed")
                    self.assertFalse(result["queryExecuted"])
                    self.assertFalse(result["oldImageDeletionAuthorized"])
                    self.assertNotIn("DO_NOT_RETURN_OR_EXTRACT", json.dumps(result))
                rows = admin.execute(sql.SQL(
                    "SELECT count(*) FROM {}.bob_android_list_images").format(
                        sql.Identifier(schema))).fetchone()
                self.assertEqual(rows[0], 1)
            finally:
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
