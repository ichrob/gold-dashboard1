"""Goal #5/#6/#10: focused diagnostic status must not hide nested defects.

Use synthetic sanitized observations only. No market/broker/network requests,
device controls or changes to data freshness/approval gates.
"""
import copy
import unittest

import bob_diagnostics as diag


class FocusedTruthTests(unittest.TestCase):
    def test_stale_one_minute_candles_make_sources_focus_partial(self):
        raw = {
            "readOnly": True, "realOrders": False,
            "observedAt": "2026-10-25T10:00:00+00:00",
            "areas": {
                "market": {
                    "status": "observed", "sessionMode": "weekend",
                    "source": {"spot_price_as_of": "2026-10-23T18:00:00+00:00"},
                    "candles": {
                        "1m": {"integrity": {"state": "stale",
                            "source": "biquote · XAU/USD Broker/MT5"}}
                    },
                },
                "sourceReliability": {"status": "observed", "sources": {}},
                "background": {"status": "ok"},
                "products": {"status": "observed", "items": [{"isin": "FAKE"}]},
            },
        }
        original = copy.deepcopy(raw)
        focused = diag.focused_report(raw, "sources")
        self.assertEqual(focused["status"], "partial")
        self.assertEqual(focused["summary"]["assessment"], "needs-attention")
        self.assertTrue(focused["readOnly"])
        self.assertFalse(focused["realOrders"])
        self.assertEqual(focused["areas"]["market"]["source"]["spot_price_as_of"],
                         "2026-10-23T18:00:00+00:00")
        self.assertNotIn("products", focused["areas"])
        self.assertEqual(raw, original)  # No original source-time rewriting.
        self.assertEqual(focused["summary"]["attention"][0]["sessionMode"], "weekend")

    def test_partial_top_level_and_nested_results_never_claim_observed(self):
        report = {
            "areas": {
                "market": {"status": "partial"},
                "analysis": {"status": "observed"},
                "background": {"status": "observed"},
            },
        }
        self.assertEqual(diag.focused_report(report, "sources")["status"], "partial")
        report["areas"]["market"] = {"status": "observed",
                                      "candles": {"5m": {"integrity": {
                                          "state": "missing"}}}}
        self.assertEqual(diag.focused_report(report, "sources")["status"], "partial")
        report["areas"]["market"] = {"status": "observed"}
        self.assertEqual(diag.focused_report(report, "sources")["status"], "observed")

    def test_source_provider_clock_is_never_replaced_with_cache_clock(self):
        report = {
            "observedAt": "2026-10-25T10:00:00+00:00",
            "areas": {
                "market": {"status": "stale",
                           "source": {"spot_price_as_of":
                                      "2026-10-24T20:59:59+00:00"},
                           "cacheAgeSeconds": 10},
                "background": {"status": "ok"},
            }
        }
        got = diag.focused_report(report, "sources")
        self.assertEqual(got["status"], "partial")
        self.assertEqual(got["areas"]["market"]["source"]["spot_price_as_of"],
                         "2026-10-24T20:59:59+00:00")
        self.assertNotEqual(got["observedAt"],
                            got["areas"]["market"]["source"]["spot_price_as_of"])

    def test_empty_focus_and_unavailable_are_not_healthy(self):
        self.assertEqual(diag.focused_report({"areas": {}}, "sources")["status"],
                         "partial")
        report = {"areas": {"background": {"status": "unavailable"}}}
        self.assertEqual(diag.focused_report(report, "sources")["status"], "partial")

    def test_unknown_focus_rejected_and_unchanged_scope(self):
        report = {"readOnly": True, "realOrders": False,
                  "areas": {"market": {"status": "observed"},
                            "products": {"status": "observed"}}}
        for unknown in ("../../admin", "broker-order", "all-accounts", ""):
            with self.subTest(unknown=unknown), self.assertRaises(ValueError):
                diag.focused_report(report, unknown)
        selected = diag.focused_report(report, "sources")
        self.assertNotIn("products", selected["areas"])
        self.assertNotIn("token", str(selected))
        self.assertEqual(diag.focused_report(report, "overview"), report)


if __name__ == "__main__":
    unittest.main()
