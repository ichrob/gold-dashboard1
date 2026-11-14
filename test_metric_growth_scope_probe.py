"""Offline assertions for operator-only redacted metric scope diagnostic."""
import json
import os
import unittest
from unittest.mock import Mock, patch

import metric_growth_scope_probe as probe


def row(kind, full, without_clock, stored=300, unavailable=False,
        mismatch=False, pointer=False):
    return (kind, full, without_clock, stored, unavailable, mismatch, pointer)


class MetricGrowthScopeProbeTests(unittest.TestCase):
    def test_only_counters_and_no_original_identity_or_hash_export(self):
        rows = [
            row("product", "a"*32, "c"*32, unavailable=True),
            row("product", "b"*32, "c"*32, unavailable=True),
            row("dmi", "d"*32, "d"*32, mismatch=True),
            row("display", "e"*32, "e"*32),
            row("trade", "f"*32, "f"*32, pointer=True),
        ]
        before = tuple(rows)
        result = probe.summarize(rows)
        self.assertEqual(tuple(rows), before)
        self.assertEqual(result["sampledRows"], 5)
        self.assertTrue(result["readOnly"])
        self.assertIsNone(result["physicalBytesFreed"])
        p = result["groups"]["product"]
        self.assertEqual(p["sampledRows"], 2)
        self.assertEqual(p["fullPayloadDigestCount"], 2)
        self.assertEqual(p["withoutCheckClockDigestCount"], 1)
        self.assertEqual(p["allUnavailableRows"], 2)
        self.assertEqual(result["groups"]["dmi"]["anyMismatchRows"], 1)
        self.assertEqual(result["groups"]["trade"]["archivePointerRows"], 1)
        public = json.dumps(result)
        for digest in ("a"*32, "b"*32, "c"*32, "d"*32, "e"*32, "f"*32):
            self.assertNotIn(digest, public)
        self.assertNotIn("PRIVATE-", public)

    def test_single_query_has_fixed_page_and_no_sql_mutation(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [
            row("product", "a"*32, "b"*32)]
        result = probe.sample(conn, now_ms=200_000_000)
        self.assertEqual(result["sampledRows"], 1)
        sql, params = conn.execute.call_args.args
        self.assertIn("FROM public.bob_metric_checks", sql)
        self.assertIn("ORDER BY checked_at DESC LIMIT 256", sql)
        self.assertIn("WITH limited AS MATERIALIZED", sql)
        self.assertNotIn("DELETE FROM", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("ALTER TABLE", sql.upper())
        self.assertNotIn("VACUUM", sql.upper())
        self.assertNotIn("payload::text AS", sql)
        self.assertEqual(params, (200_000_000 - 86_400_000,))

    def test_invalid_data_is_rejected(self):
        with self.assertRaises(ValueError):
            probe.summarize([row("product", "a"*32, "a"*32)]*257)
        bad = [
            row("private:ISIN", "a"*32, "a"*32),
            row("product", "invalid hash", "a"*32),
            row("product", "a"*32, "a"*32, stored=-1),
            row("product", "a"*32, "a"*32, stored=True),
            row("product", "a"*32, "a"*32, stored=2_000_001),
            row("product", "a"*32, "a"*32, mismatch=1),
            ("product", "a"*32),
        ]
        for value in bad:
            with self.subTest(bad=value), self.assertRaises(ValueError):
                probe.summarize([value])
        with self.assertRaises(ValueError):
            probe.sample(Mock(), now_ms=0)

    def test_no_explicit_flag_never_opens_a_connection(self):
        with patch.dict(os.environ, {"BOB_METRIC_SCOPE_PROBE_ONCE": "0"}):
            with self.assertRaises(PermissionError):
                probe.run()
        self.assertEqual(probe.summarize([])["sampledRows"], 0)
        self.assertFalse(probe.summarize([])["truncated"])

    def test_max_page_is_truncated_not_full_history(self):
        rows = [row("other", "%032x"%i, "%032x"%i)
                for i in range(256)]
        result = probe.summarize(rows)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["groups"]["other"]["sampledRows"], 256)
        self.assertIn("not-day-totals", result["scope"])


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Ephemeral CI PostgreSQL 18 required")
class MetricGrowthPgIntegrationTests(unittest.TestCase):
    def test_read_only_sql_yields_only_fixed_aggregates(self):
        # This uses GitHub Actions' disposable PostgreSQL 18 service, NEVER
        # Bob production or the separate archival restore server.
        import psycopg
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True, connect_timeout=5) as conn:
            self.assertEqual(
                conn.execute("SELECT current_database()").fetchone()[0],
                "bob_auth_test")
            conn.execute("""CREATE TEMP TABLE bob_metric_checks (
                scope text,checked_at bigint,payload jsonb)""")
            conn.execute("CREATE INDEX ON bob_metric_checks(checked_at)")
            rows = [
                ("product:private-isin-1", 199_999_100,
                 {"checkedAt": 199_999_100,
                  "metrics": {"gearing": {"status": "unavailable"}}}),
                ("product:private-isin-1", 199_999_200,
                 {"checkedAt": 199_999_200,
                  "metrics": {"gearing": {"status": "unavailable"}}}),
                ("dmi:15m", 199_999_300,
                 {"metrics": {"adx": {"status": "mismatch"}}}),
                ("trade:private", 199_999_400,
                 {"_bobColdMetricV1": {"private": "file-id"}}),
            ]
            for scope, stamp, payload in rows:
                conn.execute("""INSERT INTO pg_temp.bob_metric_checks
                    VALUES(%s,%s,%s::jsonb)""",
                    (scope, stamp, json.dumps(payload)))
            # No writes are made by the code under test.
            conn.execute("SET default_transaction_read_only=on")
            with patch.object(probe, "_SQL", probe._SQL.replace(
                    "public.bob_metric_checks", "pg_temp.bob_metric_checks")):
                result = probe.sample(conn, now_ms=200_000_000)
            self.assertEqual(result["sampledRows"], 4)
            self.assertEqual(result["groups"]["product"]["sampledRows"], 2)
            self.assertEqual(result["groups"]["product"]["allUnavailableRows"], 2)
            self.assertEqual(
                result["groups"]["product"]["withoutCheckClockDigestCount"], 1)
            self.assertEqual(
                result["groups"]["product"]["fullPayloadDigestCount"], 2)
            self.assertEqual(result["groups"]["dmi"]["anyMismatchRows"], 1)
            self.assertEqual(result["groups"]["trade"]["archivePointerRows"], 1)
            self.assertNotIn("private", json.dumps(result))
            self.assertIsNone(result["physicalBytesFreed"])


if __name__ == "__main__":
    unittest.main()
