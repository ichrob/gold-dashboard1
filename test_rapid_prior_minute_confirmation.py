"""Prospective 1-minute direction-confirmation quality-filter research."""
import copy
import json
import unittest

import rapid_leverage_study as study
import bob_diagnostics as diagnostics
from test_fast_gold_scalp_study import NOW, bundle

NAME="fast1m-impulse-prev1m"
BASE="fast1m-impulse"


class PriorClosedMinuteStudyTests(unittest.TestCase):
    def test_confirmed_pair_same_entry_and_same_exit_rules(self):
        data=bundle()
        rows,error=study.candles.minute_history(data,NOW,modeled=False)
        self.assertIsNone(error)
        sig=study.fast_signals(rows,NOW)
        self.assertEqual(sig[BASE]["direction"],"LONG")
        self.assertEqual(sig[NAME]["direction"],"LONG")
        self.assertEqual(sig[NAME],sig[BASE])
        self.assertEqual(study.FAST_POLICY[NAME],study.FAST_POLICY[BASE])
        before=copy.deepcopy(data)
        state,completed=study.advance(study.seed(NOW),data,NOW)
        self.assertEqual(data,before)
        self.assertFalse(completed)
        ref=state["arms"][BASE]["position"]
        variant=state["arms"][NAME]["position"]
        self.assertIsNotNone(variant)
        self.assertEqual(variant["pairedControl"],BASE)
        for k in ("entry","entrySourceAt","initialStop","stop","target",
                  "risk","signal","costAssumptions","direction"):
            self.assertEqual(variant[k],ref[k],k)
        self.assertFalse(variant["realOrders"])
        self.assertFalse(variant["productReturnVerified"])

    def test_unconfirmed_prior_candle_blocks_only_filtered_arm(self):
        data=bundle()
        data["history"]["bars_by_tf"]["1m"][-2].update(open=4003.,close=4003.,
             high=4004.,low=3999.)
        rows,error=study.candles.minute_history(data,NOW,modeled=False)
        self.assertIsNone(error)
        sig=study.fast_signals(rows,NOW)
        self.assertEqual(sig[BASE]["direction"],"LONG")
        self.assertIsNone(sig[NAME]["direction"])
        self.assertEqual(sig[NAME]["reason"],"no-prior-1m-confirmation")
        state,_=study.advance(study.seed(NOW),data,NOW)
        self.assertEqual(state["arms"][BASE]["started"],1)
        self.assertEqual(state["arms"][NAME]["started"],0)
        self.assertEqual(state["arms"][NAME]["lastReason"],"no-prior-1m-confirmation")
        self.assertEqual(state["arms"][NAME]["levers"]["10"]["equityEur"],1000.)

    def test_migration_keeps_all_existing_research_balances_untouched(self):
        old=study.seed(NOW-30000)
        old["arms"].pop(NAME)
        old["arms"][BASE]["started"]=100
        old["arms"][BASE]["levers"]["10"]["equityEur"]=913.45
        before=copy.deepcopy(old)
        after,_=study.advance(old,bundle(),NOW)
        self.assertEqual(old,before)
        self.assertEqual(after["arms"][BASE]["started"],100)
        self.assertEqual(after["arms"][BASE]["levers"]["10"]["equityEur"],913.45)
        self.assertEqual(after["arms"][NAME]["started"],1)
        self.assertEqual(after["arms"][NAME]["levers"]["10"]["equityEur"],1000.)

    def test_unknown_original_data_never_enters(self):
        data=bundle()
        data["history"]["bars_by_tf"]["1m"].pop(15)
        state,_=study.advance(study.seed(NOW),data,NOW)
        self.assertEqual(state["arms"][NAME]["started"],0)
        self.assertEqual(state["arms"][NAME]["lastReason"],"original-1m-coverage-missing")

    def test_observation_gap_cannot_make_fake_profit(self):
        first,_=study.advance(study.seed(NOW),bundle(),NOW)
        after,completed=study.advance(first,bundle(NOW+120000,spot=4060.),NOW+120000)
        case=next(c for c in completed if c["setup"]==NAME)
        self.assertEqual(case["status"],"inconclusive")
        self.assertIsNone(case["results"])
        self.assertEqual(after["arms"][NAME]["levers"]["10"]["equityEur"],1000.)

    def test_readonly_reporting_covers_eleven_with_seven_levers_each(self):
        state,_=study.advance(study.seed(NOW),bundle(),NOW)
        class Conn:
            def execute(self,*args):return self
            def fetchone(self):return (state,)
        source=study.report(Conn())
        self.assertEqual(len(source["setups"]),11)
        projected=diagnostics.rapid_leverage_brief(source)
        self.assertEqual(len(projected["setups"]),11)
        self.assertEqual(projected["configurationsReported"],77)
        newest=next(s for s in projected["setups"] if s["setup"]==NAME)
        self.assertEqual(newest["pairedControl"],BASE)
        self.assertEqual(newest["entryFilter"],"prior-closed-1m-same-direction")
        self.assertFalse(projected["productReturnVerified"])
        self.assertFalse(projected["strategyWinnerConfirmed"])
        self.assertNotIn("rawTrades",json.dumps(projected))

if __name__=="__main__":
    unittest.main()
