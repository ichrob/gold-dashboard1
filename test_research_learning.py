"""Deterministic tests for Bob's unattended research cycle; no order capability."""
import copy
import math
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import research_learning as learning
import strategy_lab as lab
import strategy_lab_background as worker
import strategy_lab_store as store

TZ = ZoneInfo("Europe/Zurich")


def candles(n=900):
    price=2000.0
    result=[]
    for i in range(n):
        end=price + 2.2*math.sin(i*.15)+0.45
        result.append(dict(instrument="XAU/USD", isOpen=False,
            openTime=1700000000000+i*3600000, open=price,
            close=end, high=max(price,end)+.3, low=min(price,end)-.3))
        price=end
    return result


def report(bars):
    last=bars[-1]["openTime"]
    return dict(mode="RESEARCH_ONLY", version=lab.VERSION, status="evaluated",
        approved=False, orderExecutionEnabled=False, affectsLiveSignals=False,
        brokerConnected=False, closedBars=len(bars),
        historicalInstrument="XAU/USD", rangeMs=[bars[0]["openTime"],last],
        folds=[{}]*4, evidence=dict(folds=4), outOfSampleByStrategy={
          "baseline":dict(trades=50,meanFoldNetPct=.1,worstFoldNetPct=-2,
                          maxFoldDrawdownPct=6),
          "trend-strict":dict(trades=55,meanFoldNetPct=.8,worstFoldNetPct=-1,
                              maxFoldDrawdownPct=4),
          "breakout":dict(trades=50,meanFoldNetPct=-1,worstFoldNetPct=-3,
                          maxFoldDrawdownPct=10),
          "mean-revert":dict(trades=50,meanFoldNetPct=0,worstFoldNetPct=-2,
                             maxFoldDrawdownPct=6),
        })


class AutonomousLearningTests(unittest.TestCase):
    def test_proposal_is_frozen_and_cannot_change_signals(self):
        rows=candles()
        first=learning.enrich(report(rows),rows,day="2026-10-12")
        c=first["learningCycle"]
        self.assertEqual(c["proposal"]["strategy"],"trend-strict")
        self.assertEqual(c["proposal"]["state"],"shadow")
        self.assertEqual(c["prospective"]["sessions"],0)
        self.assertEqual(c["proposal"]["frozenAtBar"],rows[-1]["openTime"])
        self.assertFalse(c["liveRuleChanged"])
        self.assertFalse(c["productNetValidated"])
        self.assertFalse(c["automaticOrder"])
        self.assertFalse(first["approved"])
        self.assertFalse(first["orderExecutionEnabled"])

    def test_only_later_closed_bars_are_used(self):
        original=candles()
        first=learning.enrich(report(original), original, day="2026-10-12")
        repeat=learning.enrich(report(original),original,first,day="2026-10-13")
        self.assertEqual(repeat["learningCycle"]["prospective"]["sessions"],0)
        later=candles(930)
        second=learning.enrich(report(later),later,first,day="2026-10-13")
        prospective=second["learningCycle"]["prospective"]
        self.assertEqual(prospective["lastEvaluatedBarAt"],later[-1]["openTime"])
        self.assertEqual(prospective["lastObservation"]["day"],"2026-10-13")
        self.assertEqual(second["learningCycle"]["proposal"]["proposedOn"],"2026-10-12")
        twice=learning.enrich(report(later),later,second,day="2026-10-14")
        self.assertEqual(twice["learningCycle"]["prospective"]["sessions"],prospective["sessions"])
        self.assertEqual(twice["learningCycle"]["prospective"]["trades"],prospective["trades"])

    def test_reject_bad_histories_and_mixed_references(self):
        rows=candles()
        base=report(rows)
        bad=copy.deepcopy(base)
        bad["outOfSampleByStrategy"]["trend-strict"]["worstFoldNetPct"]=-10
        self.assertIsNone(learning.enrich(bad,rows,day="2026-10-12")["learningCycle"]["proposal"])
        frozen=learning.enrich(base,rows,day="2026-10-12")
        changed=report(candles(931))
        changed["historicalInstrument"]="GC=F"
        result=learning.enrich(changed,candles(931),frozen,day="2026-10-13")
        self.assertEqual(result["learningCycle"]["status"],"blocked")

    def test_weekend_never_invents_evidence(self):
        rows=candles()
        before=learning.enrich(report(rows),rows,day="2026-10-12")
        maintenance=learning.maintenance(before,"2026-10-17")
        self.assertEqual(maintenance["status"],"maintenance")
        self.assertTrue(maintenance["noNewEvidence"])
        self.assertFalse(maintenance["learningCycle"]["newIndependentEvidence"])
        self.assertEqual(maintenance["learningCycle"]["proposal"],before["learningCycle"]["proposal"])
        self.assertEqual(maintenance["rangeMs"],before["rangeMs"])

    def test_weekend_archive_runs_without_fetching_quotes(self):
        self.assertIsNone(worker.trading_day(datetime(2026,10,17,12,tzinfo=TZ)))
        self.assertIsNone(worker.research_day(datetime(2026,10,17,10,tzinfo=TZ)))
        self.assertEqual(worker.research_day(datetime(2026,10,17,12,tzinfo=TZ)),"2026-10-17")
        rows=candles()
        prior=learning.enrich(report(rows),rows,day="2026-10-16")
        calls=[]
        def storage(action,payload):
            calls.append(action)
            if action=="read":
                return dict(mode="RESEARCH_ONLY",latestReport=prior,automation=dict(lastDay="2026-10-16"))
            self.assertEqual(payload["report"]["status"],"maintenance")
            return dict(saved=True,day="2026-10-17")
        outcome=worker.evaluate_and_store(
            lambda *args: self.fail("No weekend fetch expected"),
            lambda *args: self.fail("No weekend candles expected"),
            now=datetime(2026,10,17,12,tzinfo=TZ),storage=storage)
        self.assertEqual(outcome["status"],"maintenance")
        self.assertEqual(calls,["read","write"])

    def test_storage_weekends_only_accept_maintenance(self):
        rows=candles()
        before=learning.enrich(report(rows),rows,day="2026-10-16")
        m=learning.maintenance(before,"2026-10-17")
        with patch.object(store,"datetime",wraps=datetime) as dt:
            dt.now.return_value=datetime(2026,10,17,12,tzinfo=TZ)
            store.validate(dict(day="2026-10-17",report=m))
            with self.assertRaises(ValueError):
                store.validate(dict(day="2026-10-17",report=before))
            with self.assertRaises(ValueError):
                store.validate(dict(day="2026-10-17",report={**m,"noNewEvidence":False}))
            with self.assertRaises(ValueError):
                store.validate(dict(day="2026-10-17",report={**m,
                   "learningCycle":{**m["learningCycle"],"liveRuleChanged":True}}))


if __name__=="__main__":
    unittest.main()
