import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import gold_api_currency_shadow as shadow

class GoldApiCurrencyShadowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc)
        self.quotes = {c: {"symbol": "XAU", "currency": c, "price": p,
                           "updatedAt": (self.now-timedelta(seconds=20)).isoformat()}
                       for c, p in (("USD", 4000), ("EUR", 3600), ("CHF", 3200))}

    def test_cross_is_only_indicative(self):
        x = shadow.derive(self.quotes, now=self.now)
        self.assertEqual(x["kind"], "gold-api-implied-fx-shadow")
        self.assertTrue(x["researchOnly"])
        self.assertTrue(x["notForExecution"])
        self.assertTrue(x["notForProductQuotes"])
        self.assertTrue(x["notForLiveSignals"])
        self.assertAlmostEqual(x["chfToEurIndicative"], 1.125)
        self.assertAlmostEqual(x["eurToChfIndicative"], 1/1.125)
        for forbidden in ("rates", "result", "bid", "ask"):
            self.assertNotIn(forbidden, x)

    def test_fetch_once_is_bounded_and_no_key(self):
        getter = Mock(side_effect=lambda url, origin, timeout:
                      copy.deepcopy(self.quotes[url.rsplit("/", 1)[-1]]))
        x = shadow.fetch_once(fetch=getter, now=self.now)
        self.assertTrue(x["researchOnly"])
        self.assertEqual(getter.call_count, 3)
        self.assertEqual([c.args[0] for c in getter.call_args_list], list(shadow.URLS.values()))
        for c in getter.call_args_list:
            self.assertEqual(c.args[1], shadow.ORIGIN)
            self.assertEqual(c.kwargs, {"timeout": 4})

    def test_invalid_identity_price_and_timestamp_rejected(self):
        for label in ("symbol", "currency", "nan", "zero", "string",
                      "stale", "future", "naive", "skew", "missing"):
            with self.subTest(label=label):
                q = copy.deepcopy(self.quotes)
                if label == "symbol": q["EUR"]["symbol"] = "XAG"
                if label == "currency": q["EUR"]["currency"] = "CHF"
                if label == "nan": q["EUR"]["price"] = float("nan")
                if label == "zero": q["EUR"]["price"] = 0
                if label == "string": q["EUR"]["price"] = "3600"
                if label == "stale": q["EUR"]["updatedAt"] = (self.now-timedelta(seconds=61)).isoformat()
                if label == "future": q["EUR"]["updatedAt"] = (self.now+timedelta(seconds=1)).isoformat()
                if label == "naive": q["EUR"]["updatedAt"] = "2026-11-13T07:59:40"
                if label == "skew": q["EUR"]["updatedAt"] = (self.now-timedelta(seconds=10)).isoformat()
                if label == "missing": del q["EUR"]
                with self.assertRaises(ValueError):
                    shadow.derive(q, now=self.now)

    def test_compare_only_against_current_independent_live_fx(self):
        at = (self.now-timedelta(seconds=20)).isoformat()
        live = {"result": "success", "base": "USD", "source": "live",
                "sources": {"EUR": "live", "CHF": "live"}, "market_session": "open",
                "rates": {"EUR": .9, "CHF": .8}, "effective_at": {"EUR": at, "CHF": at},
                "data_updated_at": at}
        ref = shadow.derive(self.quotes, now=self.now)
        result = shadow.compare_to_live_fx(ref, live, now=self.now)
        self.assertAlmostEqual(result["eurDifferencePct"], 0)
        self.assertAlmostEqual(result["chfDifferencePct"], 0)
        self.assertTrue(result["notForExecution"])
        for bad in ({"source": "cached"}, {"market_session": "closed"},
                    {"sources": {"EUR": "cached", "CHF": "live"}},
                    {"data_updated_at": (self.now-timedelta(seconds=61)).isoformat()}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                shadow.compare_to_live_fx(ref, {**live, **bad}, now=self.now)
        with self.assertRaises(ValueError):
            shadow.compare_to_live_fx(ref, live, now=self.now+timedelta(seconds=61))

if __name__ == "__main__":
    unittest.main()
