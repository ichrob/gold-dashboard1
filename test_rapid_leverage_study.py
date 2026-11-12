import copy
import json
import unittest
from datetime import datetime, timezone

import rapid_leverage_study as s

NOW = int(datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc).timestamp()*1000)


def sample(now=NOW, *, spot=3990., last_close=3991.):
    end = int(now // s.MINUTE) * s.MINUTE
    bars = []
    for i in range(120):
        b = dict(openTime=end-(120-i)*s.MINUTE, instrument="XAU/USD",
                 source="verified-fixture", isOpen=False,
                 open=4000., high=4001., low=3999., close=4000.)
        if i >= 115:
            b.update(open=3998., high=3999., low=3990., close=last_close)
        bars.append(b)
    return dict(spots=dict(xaus=spot, is_genuine_xauusd_spot=True,
                 xaus_is_spot=True, spot_price_as_of=datetime.fromtimestamp(now/1000,timezone.utc).isoformat()),
                history=dict(bars_by_tf={"1m":bars}))


class RapidEntryTests(unittest.TestCase):
    def test_original_5m_short_breakout_and_impulse_without_main_signal(self):
        b = sample()
        rows, error = s.candles.minute_history(b, NOW, False)
        self.assertIsNone(error)
        before = copy.deepcopy(b)
        signals = s.candidate_signals(rows, NOW, events=[])
        self.assertEqual(signals["breakout"]["direction"], "SHORT")
        self.assertEqual(signals["impulse"]["direction"], "SHORT")
        self.assertEqual(signals["news-impulse"]["reason"], "no-verified-scheduled-release")
        state, finished = s.advance(s.seed(NOW), b, NOW, events=[])
        self.assertFalse(finished)
        self.assertEqual(state["arms"]["breakout"]["position"]["direction"], "SHORT")
        self.assertIsNone(state["arms"]["news-impulse"]["position"])
        self.assertEqual(b, before)
        json.dumps(state, allow_nan=False)

    def test_news_setup_requires_verified_past_release_and_price_move(self):
        rows, _ = s.candles.minute_history(sample(), NOW, False)
        future = dict(at=NOW+60000,title="future",source="BLS")
        past = dict(at=NOW-5*s.MINUTE,title="past",source="BLS")
        self.assertIsNone(s.candidate_signals(rows,NOW,[future])["news-impulse"]["direction"])
        sig=s.candidate_signals(rows,NOW,[past])["news-impulse"]
        self.assertEqual(sig["direction"],"SHORT")
        self.assertEqual(sig["event"]["at"],past["at"])

    def test_risk_budget_reduces_euro_exposure_at_higher_leverage(self):
        state, _ = s.advance(s.seed(NOW), sample(), NOW)
        p = state["arms"]["impulse"]["position"]
        self.assertIsNotNone(p)
        comparison = s.comparison(p,copy.deepcopy(state["arms"]["impulse"]),p["entry"]-3)
        self.assertLess(comparison["20"]["investedEur"],comparison["5"]["investedEur"])
        self.assertLessEqual(comparison["20"]["investedEur"],650)
        self.assertFalse(comparison["30"]["productReturnVerified"])
        self.assertGreater(comparison["20"]["sameExposureCounterfactual"]["modeledNetEur"],
                           comparison["5"]["sameExposureCounterfactual"]["modeledNetEur"])
        self.assertGreater(comparison["20"]["sameExposureCounterfactual"]["modeledStopRiskPctOfAccount"],
                           comparison["5"]["sameExposureCounterfactual"]["modeledStopRiskPctOfAccount"])
        self.assertIsNone(comparison["5"].get("confirmedTurboNetEur"))
        # Equally risk-sized spot proxies have similar gross payoff.
        self.assertAlmostEqual(comparison["10"]["grossEur"],comparison["20"]["grossEur"],places=1)

    def test_observed_stop_exits_are_not_ideal_stop_fills(self):
        old, _ = s.advance(s.seed(NOW), sample(), NOW)
        initial=old["arms"]["breakout"]["position"]
        at=NOW+30000
        new, completed=s.advance(old,sample(at,spot=4030.),at)
        p=next(x for x in completed if x["setup"]=="breakout")
        self.assertEqual(p["exitReason"],"stop-observed")
        self.assertEqual(p["exitPrice"],4030.)
        self.assertGreater(p["exitPrice"],initial["initialStop"])
        self.assertLess(p["results"]["10"]["netEur"],0)
        self.assertFalse(p["results"]["10"]["fillVerified"])
        self.assertEqual(new["arms"]["breakout"]["closed"],1)
        self.assertIsNone(new["arms"]["breakout"]["position"])

    def test_trailing_never_loosens_and_no_same_sample_reentry(self):
        old, _ = s.advance(s.seed(NOW), sample(), NOW)
        p=old["arms"]["breakout"]["position"]
        at=NOW+30000
        favorable=p["entry"]-1.15*p["risk"]
        mid,closed=s.advance(old,sample(at,spot=favorable),at)
        self.assertFalse(closed)
        advanced=mid["arms"]["breakout"]["position"]
        self.assertLessEqual(advanced["stop"],p["stop"])
        self.assertLessEqual(advanced["stop"],p["entry"])
        at2=NOW+60000
        final,completed=s.advance(mid,sample(at2,spot=p["entry"]+.5),at2)
        self.assertTrue(any(x["setup"]=="breakout" for x in completed))
        self.assertIsNone(final["arms"]["breakout"]["position"])
        self.assertEqual(final["arms"]["breakout"]["started"],1)

    def test_fresh_unmixed_original_5m_recovers_missing_1m_without_estimation(self):
        b=sample()
        rows,error=s.candles.minute_history(b,NOW,False)
        self.assertIsNone(error)
        bars=s.candles.aggregate(rows,5,NOW)
        b["history"]["bars_by_tf"]["5m"]=[
            dict(openTime=x["openTime"],open=x["open"],high=x["high"],
                 low=x["low"],close=x["close"],instrument="XAU/USD",
                 source="verified-fixture",isOpen=False)
            for x in bars]
        b["history"]["bars_by_tf"]["1m"].pop(10)
        state,_=s.advance(s.seed(NOW),b,NOW)
        self.assertEqual(state["lastInput"]["basis"],"closed-original-5m")
        self.assertEqual(state["arms"]["breakout"]["started"],1)
        self.assertFalse(state["arms"]["breakout"]["position"]["signal"]["estimated"])

    def test_original_5m_conflicts_and_gaps_are_not_reconstructed(self):
        b=sample()
        rows,_=s.candles.minute_history(b,NOW,False)
        bars=s.candles.aggregate(rows,5,NOW)
        b["history"]["bars_by_tf"]["5m"]=[
            dict(openTime=x["openTime"],open=x["open"],high=x["high"],
                 low=x["low"],close=x["close"],instrument="XAU/USD",
                 source="verified-fixture",isOpen=False)
            for x in bars]
        b["history"]["bars_by_tf"]["1m"].pop(10)
        b["history"]["bars_by_tf"]["5m"][-1]["estimated"]=True
        state,_=s.advance(s.seed(NOW),b,NOW)
        self.assertEqual(state["arms"]["breakout"]["started"],0)
        self.assertEqual(state["lastInput"]["reason"],"five-minute-original-invalid")
        b["history"]["bars_by_tf"]["5m"][-1].pop("estimated")
        b["history"]["bars_by_tf"]["5m"].pop(-5)
        state,_=s.advance(s.seed(NOW),b,NOW)
        self.assertEqual(state["arms"]["breakout"]["started"],0)
        self.assertEqual(state["lastInput"]["reason"],"five-minute-history-gap")

    def test_missing_minute_source_and_stale_data_do_not_open_positions(self):
        b=sample()
        b["history"]["bars_by_tf"]["1m"].pop(10)
        a,finished=s.advance(s.seed(NOW),b,NOW)
        self.assertFalse(finished)
        self.assertEqual(a["arms"]["breakout"]["started"],0)
        b=sample()
        b["spots"]["is_genuine_xauusd_spot"]=False
        a,_=s.advance(s.seed(NOW),b,NOW)
        self.assertEqual(a["arms"]["impulse"]["started"],0)

    def test_gap_is_inconclusive_and_does_not_book_model_profit(self):
        state,_=s.advance(s.seed(NOW),sample(),NOW)
        # Source and observation gap exceed ninety seconds; no phantom fill.
        later,completed=s.advance(state,sample(NOW+120000,spot=3950.),NOW+120000)
        self.assertTrue(completed)
        self.assertTrue(all(p["status"]=="inconclusive" and p["results"] is None for p in completed))
        self.assertEqual(later["arms"]["breakout"]["levers"]["20"]["equityEur"],1000.)

    def test_no_double_consumption_and_no_mutation(self):
        state,_=s.advance(s.seed(NOW),sample(),NOW)
        frozen=copy.deepcopy(state)
        same,closed=s.advance(state,sample(),NOW)
        self.assertEqual(same,frozen)
        self.assertFalse(closed)
        self.assertEqual(state,frozen)

    def test_model_review_requires_complete_comparable_original_outcomes(self):
        arm=s.seed(NOW)['arms']['impulse']
        none=s.model_review(arm)
        self.assertEqual(none['status'],'insufficient-comparable-evidence')
        self.assertIsNone(none['exploratoryModelLeader'])
        for k,slot in arm['levers'].items():
            slot.update(completed=20,netEur=5.*int(k),excluded=0,maxDrawdownPct=3.)
        arm.update(started=20,closed=20,inconclusive=1)
        self.assertIsNone(s.model_review(arm)['exploratoryModelLeader'])
        arm['inconclusive']=0
        review=s.model_review(arm)
        self.assertEqual(review['status'],'exploratory-proxy-only')
        self.assertEqual(review['exploratoryModelLeader'],30)
        self.assertFalse(review['netProductVerified'])
        arm['levers']['30']['excluded']=1
        self.assertIsNone(s.model_review(arm)['exploratoryModelLeader'])
        arm['levers']['30']['excluded']=0
        arm['levers']['30']['completed']=19
        self.assertIsNone(s.model_review(arm)['exploratoryModelLeader'])

    def test_no_strategy_promotion_and_paper_only(self):
        st=s.seed(NOW)
        self.assertEqual(set(st["arms"]),set(s.SETUPS))
        self.assertEqual(len(st["arms"]["impulse"]["levers"]),7)
        self.assertNotIn("broker",s.NOTE.lower())
        self.assertFalse(s.local_session(int(datetime(2026,11,8,16,tzinfo=timezone.utc).timestamp()*1000)))


if __name__=="__main__":
    unittest.main()
