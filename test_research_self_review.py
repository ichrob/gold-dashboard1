"""Regression tests: self-review cannot promote strategies or issue orders."""
import copy
import unittest

import research_self_review as audit
import research_learning as learning


def cycle(*, sessions=20, trades=30, better=True):
    baseline = dict(index=1.05, maxDrawdownPct=9.0, trades=trades)
    candidate = dict(index=1.14 if better else .93,
                     maxDrawdownPct=6.0 if better else 15.0, trades=trades)
    group = dict(costBpsPerSide=8, baseline=baseline, candidate=candidate)
    stress = copy.deepcopy(group)
    stress["costBpsPerSide"] = 24
    stress["candidate"]["index"] = 1.10 if better else .91
    stress["baseline"]["index"] = 1.03
    return dict(prospective=dict(sessions=sessions, trades=trades, baselineTrades=trades,
        costScenarios=dict(standard=group, stress=stress)))


class SelfReviewTests(unittest.TestCase):
    def test_no_evidence_never_claims_confidence(self):
        r = audit.review({})
        self.assertEqual(r["status"], "insufficient")
        self.assertFalse(r["actionable"])
        self.assertFalse(r["liveRuleChanged"])
        self.assertFalse(r["automaticOrder"])

    def test_no_candidate_is_not_reported_as_broken_cost_test(self):
        r=audit.review(learning._new_cycle())
        self.assertEqual(r['status'],'insufficient')
        self.assertIn('wartet auf einen eingefrorenen Kandidaten',r['reason'])
        self.assertFalse(r['actionable'])
        self.assertEqual(r['comparedScenarios'],{})

    def test_paired_stress_and_independent_sample_gate(self):
        a = audit.review(cycle())
        self.assertEqual(a["status"], "reference-promising")
        self.assertEqual(a["confidence"], "reference-only")
        self.assertFalse(a["productNetValidated"])
        self.assertFalse(a["actionable"])
        self.assertGreater(a["comparedScenarios"]["stress"]["relativeDifferencePct"], 0)
        self.assertEqual(audit.review(cycle(sessions=4))["status"], "collecting")
        self.assertEqual(audit.review(cycle(trades=14))["status"], "collecting")

    def test_losing_stress_or_missing_evidence_never_passes(self):
        self.assertEqual(audit.review(cycle(better=False))["status"],
                         "reference-unreliable")
        broken = cycle()
        del broken["prospective"]["costScenarios"]["stress"]
        self.assertEqual(audit.review(broken)["status"], "insufficient")
        bad = cycle()
        bad["prospective"]["costScenarios"]["stress"]["candidate"]["index"] = float("nan")
        self.assertEqual(audit.review(bad)["status"], "insufficient")
        invalid = cycle()
        invalid["prospective"]["sessions"] = True
        self.assertEqual(audit.review(invalid)["status"], "insufficient")

    def test_recent_ten_unfavorable_paired_windows_flag_caution(self):
        p = cycle()
        p["prospective"]["recentComparisons"] = [
            dict(lastBarAt=1700000000000+i*3600000,
                 candidateNetReturnPct=-1 if i < 7 else 3,
                 baselineNetReturnPct=0)
            for i in range(10)]
        x = audit.review(p)
        self.assertEqual(x["status"], "recently-unreliable")
        self.assertEqual(x["recentWindows"]["underperformingOrEqualIntervals"], 7)
        p["prospective"]["recentComparisons"][3]["lastBarAt"] = p["prospective"]["recentComparisons"][2]["lastBarAt"]
        self.assertIsNone(audit.review(p)["recentWindows"])

    def test_existing_learning_produces_critical_read_only_metadata(self):
        from test_research_learning import candles, report
        bars = candles()
        enriched = learning.enrich(report(bars), bars, day="2026-10-22")
        self.assertEqual(enriched["learningCycle"]["selfReview"]["status"], "insufficient")
        self.assertFalse(enriched["learningCycle"]["selfReview"]["actionable"])
        self.assertFalse(enriched["approved"])
        self.assertFalse(enriched["orderExecutionEnabled"])
        weekend = learning.maintenance(enriched, "2026-10-24")
        self.assertFalse(weekend["learningCycle"]["selfReview"]["automaticOrder"])
        self.assertFalse(weekend["learningCycle"]["newIndependentEvidence"])


if __name__ == "__main__":
    unittest.main()
