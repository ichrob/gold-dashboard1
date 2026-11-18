"""Regression tests for forward-only quick Gold shadow trading hypotheses."""
import copy
import unittest
from datetime import datetime, timezone

import rapid_leverage_study as s

NOW = int(datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)


def bundle(now=NOW, *, spot=4008.0):
    end=(now//s.MINUTE)*s.MINUTE
    bars=[]
    for i in range(120):
        t=end-(120-i)*s.MINUTE
        bars.append(dict(openTime=t,instrument="XAU/USD",source="fixture-original",
                         isOpen=False,providerIsOpen=False,estimated=False,
                         open=4000.,high=4001.,low=3999.,close=4000.))
    bars[-3].update(open=3999.,high=4001.,low=3998.,close=4000.)
    bars[-2].update(open=4000.,high=4004.,low=3999.,close=4003.)
    bars[-1].update(open=4003.,high=4009.,low=4002.,close=4008.)
    return dict(spots=dict(xaus=spot,is_genuine_xauusd_spot=True,
                           xaus_is_spot=True,
                           spot_price_as_of=datetime.fromtimestamp(
                               now/1000,timezone.utc).isoformat()),
                history=dict(bars_by_tf=dict(**{"1m":bars})))


class FastProspectiveRegression(unittest.TestCase):
    def test_three_distinct_fast_original_signals(self):
        data=bundle()
        rows,error=s.candles.minute_history(data,NOW,modeled=False)
        self.assertIsNone(error)
        sig=s.fast_signals(rows,NOW)
        self.assertEqual({x["direction"] for x in sig.values()},{"LONG"})
        self.assertEqual(set(sig),s.FAST_SETUPS)
        self.assertTrue(all(x["originalMinuteOnly"] for x in sig.values()))
        self.assertTrue(all(x["closedAt"]<=NOW for x in sig.values()))

    def test_fast_positions_open_independently_from_main_trend(self):
        data=bundle()
        before=copy.deepcopy(data)
        state,closed=s.advance(s.seed(NOW),data,NOW)
        self.assertFalse(closed)
        self.assertEqual(data,before)
        for name in s.FAST_SETUPS:
            p=state["arms"][name]["position"]
            self.assertIsNotNone(p,name)
            self.assertEqual(p["direction"],"LONG")
            self.assertFalse(p["productReturnVerified"])
            self.assertLessEqual(p["target"]-p["entry"],1.8*p["risk"]+1e-6)

    def test_preserves_existing_four_cohorts_on_migration(self):
        previous=s.seed(NOW)
        for name in s.FAST_SETUPS:
            del previous["arms"][name]
        previous["arms"]["breakout"]["started"]=100
        previous["arms"]["breakout"]["levers"]["10"]["equityEur"]=943.21
        later,closed=s.advance(previous,bundle(),NOW)
        self.assertEqual(later["arms"]["breakout"]["started"],100)
        self.assertEqual(later["arms"]["breakout"]["levers"]["10"]["equityEur"],943.21)
        self.assertTrue(all(n in later["arms"] for n in s.FAST_SETUPS))
        self.assertNotEqual(previous,later)

    def test_observed_target_and_no_same_observation_reentry(self):
        opened,_=s.advance(s.seed(NOW),bundle(),NOW)
        later,finished=s.advance(opened,bundle(NOW+30000,spot=4050.),NOW+30000)
        self.assertTrue(any(x["setup"]=="fast1m-impulse" for x in finished))
        closed=next(x for x in finished if x["setup"]=="fast1m-impulse")
        self.assertEqual(closed["exitReason"],"target-observed")
        self.assertEqual(closed["exitPrice"],4050.)
        self.assertEqual(later["arms"]["fast1m-impulse"]["started"],1)
        self.assertIsNone(later["arms"]["fast1m-impulse"]["position"])
        self.assertFalse(closed["results"]["10"]["fillVerified"])

    def test_observation_gap_cannot_create_profit(self):
        state,_=s.advance(s.seed(NOW),bundle(),NOW)
        later,finished=s.advance(state,bundle(NOW+120000,spot=4020.),NOW+120000)
        fast=[x for x in finished if x["setup"] in s.FAST_SETUPS]
        self.assertTrue(fast)
        self.assertTrue(all(x["status"]=="inconclusive" for x in fast))
        self.assertTrue(all(x["results"] is None for x in fast))
        self.assertEqual(later["arms"]["fast1m-impulse"]["levers"]["10"]["equityEur"],1000.)

    def test_no_fast_entry_without_original_minute_series(self):
        data=bundle()
        data["history"]["bars_by_tf"]["1m"].pop(15)
        state,_=s.advance(s.seed(NOW),data,NOW)
        for name in s.FAST_SETUPS:
            self.assertEqual(state["arms"][name]["started"],0)
            self.assertEqual(state["arms"][name]["lastReason"],"original-1m-coverage-missing")

    def test_daily_loss_guard_blocks_without_affecting_legacy(self):
        state=s.seed(NOW)
        for name in s.FAST_SETUPS:
            arm=state["arms"][name]
            arm["riskDay"]="2026-11-18"
            arm["dayStartEur"]=1000.
            arm["levers"]["10"]["equityEur"]=965.
        later,_=s.advance(state,bundle(),NOW)
        self.assertTrue(all(later["arms"][name]["lastReason"]=="fast-daily-loss-limit"
                            for name in s.FAST_SETUPS))
        self.assertNotEqual(later["arms"]["impulse"]["lastReason"],"fast-daily-loss-limit")

    def test_fast_exit_stop_tightens_not_loosens(self):
        state,_=s.advance(s.seed(NOW),bundle(),NOW)
        pos=state["arms"]["fast1m-impulse"]["position"]
        gain=pos["entry"]+0.9*pos["risk"]
        follow,_=s.advance(state,bundle(NOW+30000,spot=gain),NOW+30000)
        open_case=follow["arms"]["fast1m-impulse"]["position"]
        self.assertIsNotNone(open_case)
        self.assertGreaterEqual(open_case["stop"],pos["stop"])
        self.assertGreaterEqual(open_case["stop"],pos["entry"])


if __name__=="__main__":
    unittest.main()
