"""Forward-only original-price paper study. No database or market network."""
import copy
import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import early_warning_spot_study as study

Z = ZoneInfo("Europe/Zurich")
BAR = int(datetime(2026,11,12,21,40,tzinfo=Z).timestamp()*1000)
SOURCE = BAR + 300000 + 6000  # 21:45:06, shortly after the closed 5m bar.


def sample(direction="SHORT", price=3881.9, source=SOURCE):
    market = dict(ready=True, priceFresh=True, direction="NEUTRAL", atr=5.9,
                  price=price, dataAt=source, ruleVersion="intraday-trend-follow-v7",
                  earlyWarning=dict(version="early-warning-v2", available=True,
                                    state="active", direction=direction,
                                    signalBarAt=BAR+300000, expiresAt=BAR+1200000,
                                    comparisonOnly=True, affectsApproval=False,
                                    extensionRisk=False))
    quality = dict(verified=True, sourceAt=source, price=price,
                   fiveMinuteCloseAt=BAR+300000)
    return market, quality


class EarlySpotTests(unittest.TestCase):
    def test_start_before_main_and_frozen_short_stop_target(self):
        market, quality = sample()
        self.assertTrue(study.warning_eligible(market, quality, SOURCE))
        state = study.new_case(market, quality)
        self.assertFalse(state["realOrders"])
        self.assertFalse(state["productReturnVerified"])
        self.assertEqual(state["arms"]["early"]["entryPrice"], 3881.9)
        self.assertAlmostEqual(state["arms"]["early"]["stop"], 3887.8)
        self.assertAlmostEqual(state["arms"]["early"]["target"], 3873.05)
        self.assertEqual(state["arms"]["confirmed"]["status"], "waiting")

    def test_later_confirmation_and_observed_target_costs_are_distinct(self):
        market, quality = sample()
        initial = study.new_case(market, quality)
        m2, q2 = sample(price=3880., source=SOURCE+30000)
        m2["direction"] = "SHORT"
        running = study.progress(initial, m2, q2, SOURCE+30000)
        self.assertEqual(running["arms"]["confirmed"]["entryAt"], SOURCE+30000)
        m3, q3 = sample(price=3870., source=SOURCE+60000)
        finished = study.progress(running, m3, q3, SOURCE+60000)
        self.assertEqual(finished["status"], "complete")
        self.assertEqual(finished["arms"]["early"]["exitReason"], "observed-target")
        self.assertEqual(finished["arms"]["confirmed"]["exitReason"], "observed-target")
        self.assertIsInstance(finished["pairedSpotDifferencePct"], float)
        self.assertEqual(initial["arms"]["confirmed"]["status"], "waiting")

    def test_missing_main_confirmation_is_not_a_fictitious_main_fill(self):
        market, quality = sample()
        s = study.new_case(market, quality)
        m2, q2 = sample(price=3870., source=SOURCE+30000)
        s = study.progress(s, m2, q2, SOURCE+30000)
        self.assertEqual(s["arms"]["early"]["status"], "closed")
        for timestamp in range(SOURCE+60000, s["deadlineAt"]+1, 30000):
            m3,q3 = sample(price=3870., source=timestamp)
            s = study.progress(s, m3, q3, timestamp)
        m3,q3 = sample(price=3870., source=s["deadlineAt"])
        s = study.progress(s, m3, q3, s["deadlineAt"])
        self.assertEqual(s["arms"]["confirmed"]["status"], "no-entry")
        self.assertEqual(s["status"], "complete")
        self.assertNotIn("pairedSpotDifferencePct", s)

    def test_never_price_stale_or_unverified_samples(self):
        market, quality = sample()
        s = study.new_case(market, quality)
        bad = {**quality, "verified":False, "sourceAt":SOURCE+30000, "price":3870.}
        s1 = study.progress(s, market, bad, SOURCE+30000)
        self.assertEqual(s1["arms"]["early"]["status"], "open")
        s2 = study.progress(s1, market, bad, SOURCE+study.GAP_MS+1000)
        self.assertEqual(s2["arms"]["early"]["status"], "inconclusive")
        self.assertNotIn("modelSpotReturnPct", s2["arms"]["early"])
        later = {**quality, "sourceAt":SOURCE+120000, "price":3870.}
        s3 = study.progress(s, market, later, SOURCE+120000)
        self.assertEqual(s3["status"], "inconclusive")

    def test_invalid_warning_cannot_open_or_backfill(self):
        m,q = sample()
        for invalid in ({"state":"watch"},{"extensionRisk":True},
                        {"signalBarAt":BAR},{"affectsApproval":True}):
            clone = copy.deepcopy(m)
            clone["earlyWarning"].update(invalid)
            self.assertFalse(study.warning_eligible(clone,q,SOURCE))
        self.assertFalse(study.warning_eligible(m,{**q,"verified":False},SOURCE))
        self.assertFalse(study.warning_eligible(m,{**q,"sourceAt":SOURCE-61000},SOURCE))
        # A quote from before the 5m close is look-ahead, even if current.
        self.assertFalse(study.warning_eligible(m,{**q,"sourceAt":BAR+300000-1000},SOURCE))

    def test_original_five_minute_candle_requires_source_and_closed_state(self):
        from test_paper_shadow_studies import observed
        from test_paper_ko_guard import NOW
        bundle, market = observed(at=NOW, direction="NEUTRAL")
        bar = (NOW // 300000 - 1) * 300000
        bundle["history"]["bars_by_tf"]["5m"] = [
            dict(instrument="XAU/USD",openTime=bar,isOpen=False)]
        old = copy.deepcopy((bundle,market))
        accepted = study.original(bundle,market,NOW)
        self.assertTrue(accepted["verified"])
        self.assertEqual((bundle,market),old)
        for change in ("open","estimated","wrong-instrument","source-mismatch"):
            bad = copy.deepcopy(bundle)
            m = copy.deepcopy(market)
            candle = bad["history"]["bars_by_tf"]["5m"][0]
            if change == "open": candle["isOpen"] = True
            if change == "estimated": candle["estimated"] = True
            if change == "wrong-instrument": candle["instrument"] = "XAU/USD Future"
            if change == "source-mismatch": bad["spots"]["xaus"] += 10
            self.assertFalse(study.original(bad,m,NOW)["verified"],change)

    def test_diagnostic_preview_exposes_no_fake_product_profit(self):
        m,q = sample();s=study.new_case(m,q)
        class FakeConn:
            def execute(self, sql):
                self.sql=sql
                return self
            def fetchall(self):
                return [(s,)]
        out = study.report(FakeConn())
        self.assertEqual(out["open"],1)
        self.assertFalse(out["productReturnVerified"])
        self.assertEqual(out["pairedCompleted"],0)
        self.assertEqual(out["pairedSpotDifferencePctSum"],0)
        self.assertNotIn("modelNetEur",json.dumps(out))


if __name__ == "__main__":
    unittest.main()
