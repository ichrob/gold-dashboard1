"""Prospective quality study: transient rejected ticks are not fictitious >90s gaps.

No interpolation, no product trade, and old persisted outcomes remain immutable.
"""
import unittest
import research_restart as research
from test_research_restart import NOW, sample


class OriginalRecovery(unittest.TestCase):
    def test_one_bad_spot_recovers_at_60_seconds_with_original_exit(self):
        bundle, market = sample()
        state, closed = research.advance(research.seed(NOW), bundle, market, NOW)
        self.assertFalse(closed)
        invalid_bundle, invalid_market = sample(NOW+30000)
        invalid_bundle["spots"]["is_genuine_xauusd_spot"] = False
        state, closed = research.advance(state, invalid_bundle, invalid_market, NOW+30000)
        self.assertFalse(closed)
        self.assertEqual(state["quality"]["invalid"], 1)
        for study in state["studies"].values():
            case=study["open"][0]
            self.assertFalse(case["dataGap"])
            self.assertEqual(case["invalidOriginalChecks"],1)
            self.assertEqual(case["inputGapPolicy"],"original-observed-over-90s-v2")
        bundle, market = sample(NOW+60000, 4001.)
        state, closed = research.advance(state,bundle,market,NOW+60000)
        self.assertFalse(closed)
        delayed=state["studies"]["entry-delay"]["open"][0]
        # The 30s leg is only observed at the genuine 60s clock: never backdate.
        self.assertEqual(delayed["legs"]["30s"]["entry"]["at"],NOW+60000)
        self.assertEqual(delayed["legs"]["60s"]["entry"]["at"],NOW+60000)
        outcomes=[]
        for elapsed in range(90000,3600001,30000):
            bundle,market=sample(NOW+elapsed, 4000.+elapsed/180000)
            state,finished=research.advance(state,bundle,market,NOW+elapsed)
            outcomes.extend(finished)
        self.assertEqual(len(outcomes),3)
        self.assertTrue(all(c["status"]=="complete" and not c["dataGap"]
                            and c["invalidOriginalChecks"]==1
                            and c["exit"]["at"]==c["endAt"] for c in outcomes))
        self.assertEqual(state["quality"]["invalid"],1)

    def test_prolonged_original_gap_stays_inconclusive(self):
        bundle,market=sample()
        state,_=research.advance(research.seed(NOW),bundle,market,NOW)
        for elapsed in (30000,60000,90000,120000):
            bundle,market=sample(NOW+elapsed)
            bundle["spots"]["is_genuine_xauusd_spot"] = False
            state,_=research.advance(state,bundle,market,NOW+elapsed)
        self.assertTrue(all(a["open"][0]["dataGap"] for a in state["studies"].values()))
        outputs=[]
        for elapsed in range(150000,3600001,30000):
            bundle,market=sample(NOW+elapsed,4000.+elapsed/180000)
            state,finished=research.advance(state,bundle,market,NOW+elapsed)
            outputs.extend(finished)
        self.assertEqual(len(outputs),3)
        self.assertTrue(all(c["status"]=="inconclusive" and not c["returnsPct"]
                            for c in outputs))

    def test_worker_over_90_seconds_remains_a_gap(self):
        bundle,market=sample()
        state,_=research.advance(research.seed(NOW),bundle,market,NOW)
        bundle,market=sample(NOW+120000)
        state,_=research.advance(state,bundle,market,NOW+120000)
        self.assertTrue(all(a["open"][0]["dataGap"] for a in state["studies"].values()))

    def test_retained_enqueue_observations_do_not_become_a_worker_gap(self):
        bundle,market=sample()
        state,_=research.advance(research.seed(NOW),bundle,market,NOW)
        # Production witness: selected source clocks are exactly 90s apart,
        # while retained full enqueue candidates prove the worker kept running.
        # The final tick's processing clock is 74ms over the wall threshold.
        bundle,market=sample(NOW+90000)
        observations=[NOW+39781, NOW+59795, NOW+90000]
        state,_=research.advance(
            state,bundle,market,NOW+90074,
            worker_observations=observations)
        self.assertEqual(state["quality"]["missingIntervals"],0)
        self.assertTrue(all(not a["open"][0]["dataGap"]
                            for a in state["studies"].values()))

    def test_actual_enqueue_observation_gap_keeps_strict_90_second_gate(self):
        bundle,market=sample()
        state,_=research.advance(research.seed(NOW),bundle,market,NOW)
        bundle,market=sample(NOW+120000)
        state,_=research.advance(
            state,bundle,market,NOW+120000,
            worker_observations=[NOW+90001])
        self.assertEqual(state["quality"]["missingIntervals"],1)
        self.assertTrue(all(a["open"][0]["dataGap"]
                            for a in state["studies"].values()))


if __name__=="__main__":
    unittest.main()
