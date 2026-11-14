"""No production SQL, credentials, market prices or external connectors."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

import metric_growth_scope_probe as probe


def row(scope, n, payload):
    return (scope, n, json.dumps(payload, ensure_ascii=False), 300)


class MetricGrowthScopeProbeTests(unittest.TestCase):
    def test_only_aggregates_and_preserves_distinct_check_times(self):
        original = [
            row("product:PRIVATE-ISIN-1", 1000, {
                "checkedAt": 1000, "metrics": {"gearing": {"status": "unavailable"}},
                "source": "PRIVATE-QUOTE-SOURCE"}),
            row("product:PRIVATE-ISIN-1", 2000, {
                "checkedAt": 2000, "metrics": {"gearing": {"status": "unavailable"}},
                "source": "PRIVATE-QUOTE-SOURCE"}),
            row("dmi:15m", 3000, {"checkedAt": 3000,
                "metrics": {"adx": {"status": "mismatch"}}}),
            row("display:1m", 4000, {"checkedAt": 4000,
                "metrics": {"R": {"status": "matched"}}}),
            row("trade:PRIVATE-ID", 5000, {"checkedAt": 5000,
                "_bobColdMetricV1": {"secret": "PRIVATE-FILE-ID"}}),
        ]
        before = copy.deepcopy(original)
        result = probe.summarize(original)
        self.assertEqual(original, before)
        self.assertEqual(result["sampledRows"], 5)
        self.assertTrue(result["readOnly"])
        self.assertIsNone(result["physicalBytesFreed"])
        product = result["groups"]["product"]
        self.assertEqual(product["sampledRows"], 2)
        self.assertEqual(product["fullPayloadDigestsDistinct"], 2)
        self.assertEqual(product["withoutCheckClockDigestsDistinct"], 1)
        self.assertEqual(product["allUnavailableRows"], 2)
        self.assertEqual(result["groups"]["dmi"]["anyMismatchRows"], 1)
        self.assertEqual(result["groups"]["trade"]["archivePointerRows"], 1)
        public_output = json.dumps(result)
        for private in ("PRIVATE-ISIN-1", "PRIVATE-ID", "PRIVATE-FILE-ID",
                        "PRIVATE-QUOTE-SOURCE", "1000", "2000"):
            self.assertNotIn(private, public_output)
        self.assertNotIn("PRIVATE-", public_output)

    def test_does_not_call_mutating_sql_or_unbounded_queries(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [
            row("product:secret", 1000, {"checkedAt": 1000, "metrics": {}})
        ]
        result = probe.sample(conn, now_ms=200_000_000)
        self.assertEqual(result["sampledRows"], 1)
        query, parameters = conn.execute.call_args.args
        self.assertIn("FROM public.bob_metric_checks", query)
        self.assertIn("ORDER BY checked_at DESC", query)
        self.assertIn("LIMIT 256", query)
        self.assertNotIn("DELETE", query.upper())
        self.assertNotIn("UPDATE", query.upper())
        self.assertNotIn("ALTER", query.upper())
        self.assertNotIn("VACUUM", query.upper())
        self.assertEqual(parameters, (200_000_000 - 86_400_000,))

    def test_bad_sizes_types_and_oversized_samples_rejected(self):
        with self.assertRaises(ValueError):
            probe.summarize([row("product:abc", 1, {})] * 257)
        for candidate in [
            (42, 3, "{}", 3),
            ("product:x", 3, "{}", -1),
            ("product:x", 3, "{}", 16385),
            ("product:x", 3, '{"nan":NaN}', 3),
            ("product:x", 3, '"' + "x" * 16000 + '"', 3),
            ("product:x", 3, '{"large":"' + "x" * 16384 + '"}', 3),
            ("product:x", 3, "[]", 3),
        ]:
            with self.subTest(candidate=str(candidate)[:45]), self.assertRaises(ValueError):
                probe.summarize([candidate])
        with self.assertRaises(ValueError):
            probe.sample(Mock(), now_ms=0)

    def test_no_opt_in_prevents_any_db_connection(self):
        # A missing or false flag must stop before importing or opening psycopg.
        with patch.dict(os.environ, {"BOB_METRIC_SCOPE_PROBE_ONCE": "0"}):
            with self.assertRaises(PermissionError):
                probe.run()
        self.assertEqual(probe.summarize([])["sampledRows"], 0)
        self.assertFalse(probe.summarize([])["truncated"])

    def test_limit_is_finite_and_does_not_claim_full_coverage(self):
        sample = [row("other:fixture", i, {"checkedAt": i}) for i in range(256)]
        result = probe.summarize(sample)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["groups"]["other"]["sampledRows"], 256)
        self.assertIn("not-day-totals", result["scope"])


if __name__ == "__main__":
    unittest.main()
