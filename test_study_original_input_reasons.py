"""Focused prospective study source-failure diagnosis; synthetic only.

No market fetch, database mutation, trades, or invented original quotes.
"""
import copy
import unittest
from test_paper_shadow_studies import observed, NOW
import paper_shadow_studies as inputs
import research_restart as campaign
import bob_diagnostics as diag


class OriginalInputReasonTests(unittest.TestCase):
    def test_one_safe_precise_cause_per_rejected_original(self):
        original_bundle, original_market = observed()
        examples = {
            "spot-identity-unverified": lambda b,m: b["spots"].update(is_genuine_xauusd_spot=False),
            "spot-source-clock-missing": lambda b,m: b["spots"].update(spot_price_as_of=None),
            "spot-or-analysis-price-invalid": lambda b,m: b["spots"].update(xaus=-1),
            "spot-analysis-price-mismatch": lambda b,m: b["spots"].update(xaus=5000),
            "analysis-not-ready": lambda b,m: m.update(ready=False),
            "analysis-price-not-fresh": lambda b,m: m.update(priceFresh=False),
            "analysis-source-clock-mismatch": lambda b,m: m.update(dataAt=NOW-5000),
            "original-signal-bar-missing": lambda b,m: b["history"]["bars_by_tf"]["15m"].clear(),
        }
        self.assertIsNone(inputs.original_input(original_bundle,original_market,NOW)["reasonCode"])
        for expected, change in examples.items():
            with self.subTest(expected=expected):
                b=copy.deepcopy(original_bundle);m=copy.deepcopy(original_market)
                change(b,m)
                result=inputs.original_input(b,m,NOW)
                self.assertFalse(result["verified"])
                self.assertEqual(result["reasonCode"],expected)
                self.assertIn(expected,inputs.ORIGINAL_INPUT_REASONS)
        b=copy.deepcopy(original_bundle)
        result=inputs.original_input(b,original_market,NOW+61000)
        self.assertEqual(result["reasonCode"],"spot-source-not-fresh")

    def test_original_campaign_counts_causal_blocks_without_changing_decisions(self):
        b,m=observed()
        before=copy.deepcopy((b,m))
        blocked=copy.deepcopy(m)
        blocked["priceFresh"]=False
        state,closed=campaign.advance(campaign.seed(NOW),b,blocked,NOW)
        self.assertEqual(state["quality"]["invalid"],1)
        self.assertEqual(state["quality"]["originalBlockReasons"],
                         {"analysis-price-not-fresh":1})
        self.assertEqual(state["quality"]["lastOriginalBlockCode"],"analysis-price-not-fresh")
        self.assertEqual(state["quality"]["lastOriginalBlockAt"],NOW)
        self.assertEqual(sum(x["started"] for x in state["studies"].values()),0)
        self.assertEqual(closed,[])
        state,_=campaign.advance(state,b,blocked,NOW+1000)
        self.assertEqual(state["quality"]["originalBlockReasons"]["analysis-price-not-fresh"],2)
        self.assertEqual((b,m),before)

    def test_modelled_candle_counts_original_rejection_but_not_invalid_model(self):
        b,m=observed()
        b["history"]["bars_by_tf"]["15m"] = [
            {"openTime":m["analysisBarAt"]-900000, "instrument":"XAU/USD",
             "isOpen":False, "close":3998.0}]
        state,_=campaign.advance(campaign.seed(NOW),b,m,NOW,modeled=True)
        self.assertEqual(state["quality"]["originalBlockReasons"],{"original-signal-bar-missing":1})
        self.assertEqual(state["quality"]["invalid"],0)
        self.assertEqual(state["quality"]["estimated"],1)
        self.assertEqual(state["studies"]["entry-delay"]["started"],1)
        self.assertFalse(state["lastInput"]["verified"])

    def test_compact_diagnostics_projects_only_fixed_codes_and_counts(self):
        paper={
            "qualityCampaign":{"status":"collecting","checkedAt":NOW,
              "studies":[{"id":"reaction","cycles":10,"invalid":2,
                "originalBlockReasons":{"analysis-price-not-fresh":2,
                 "private-ISIN-token":1000,"spot-source-not-fresh":True,
                 "spot-source-clock-missing":-1},
                 "lastOriginalBlockCode":"analysis-price-not-fresh"}],
              "modeledSimulation":{"status":"collecting","studies":[]}},
            "shadowStudies":{"status":"observed","entryExitComparison":{"status":"collecting"}},
            "intradayTimingStudy":{"status":"collecting"},
        }
        original=copy.deepcopy(paper)
        result=diag.new_studies_brief(paper,now_ms=NOW)
        found=result["quality"]["studies"][0]
        self.assertEqual(found["originalBlockReasons"],{"analysis-price-not-fresh":2})
        self.assertEqual(found["recentOriginalBlockCode"],"analysis-price-not-fresh")
        self.assertEqual(paper,original)
        self.assertNotIn("private-ISIN-token",str(result))
        self.assertFalse(result["strategyWinnerConfirmed"])
        self.assertFalse(result["fullOriginalHistoryVerified"])

if __name__ == "__main__":
    unittest.main()
