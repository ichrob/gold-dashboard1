"""Gold short-hold experiments: forward-only clocks, risk and privacy."""
import copy
import json
import unittest
from datetime import datetime,timezone
from unittest.mock import patch

import gold_short_scenarios as s
import intraday_timing_study as candles

NOW=int(datetime(2026,11,19,15,30,15,tzinfo=timezone.utc).timestamp()*1000)
SOURCE=NOW-3000
def market(direction="LONG",adx=30,now=NOW,spot=103.):
    return dict(ready=True,priceFresh=True,direction=direction,price=spot,
        dataAt=now-3000,analysisBarAt=now-15*s.MINUTE,
        session=dict(entryAllowed=True),
        trendContext=dict(direction=direction,available=True,intact=True),
        dmi=dict(frames={
            "15m":dict(direction=direction,adx=adx),
            "1h":dict(direction=direction,adx=33)}),
        analysisSnapshot=dict(e20=106.,e50=100.))

def sig(family="trend-reentry",side="LONG",now=NOW):
    sign=1 if side=="LONG" else -1
    return dict(direction=side,kind=family,barAt=now-5*s.MINUTE,
                closedAt=now-15000,close=103.,atr=3.,
                stopAnchor=103.-sign*2.,
                targetAnchor=103.+sign*5.)

def source(spot=103.,at=SOURCE):
    return dict(available=True,at=at,price=spot,estimated=False)


class ShortGoldScenarioTests(unittest.TestCase):
    def test_exactly_three_strategy_families_with_prespecified_bounded_grid(self):
        self.assertEqual(len(s.ARM_CONFIG),22)
        self.assertEqual(set(s.FAMILIES),{"trend-reentry","breakout-retest","false-breakout"})
        self.assertEqual(s.LEVERS,(5,10,20))
        self.assertEqual(s.ARM_CONFIG["trend-reentry:adx20"]["adx"],20)
        self.assertEqual(s.ARM_CONFIG["trend-reentry:age25"]["ageMinutes"],25)
        self.assertEqual(s.ARM_CONFIG["trend-reentry:drift11"]["driftAtr"],1.1)
        self.assertEqual(s.ARM_CONFIG["trend-reentry:rr20"]["minRR"],2.)
        self.assertEqual(s.ARM_CONFIG["trend-reentry:stop10"]["noProgressMinutes"],10)
        self.assertEqual(s.ARM_CONFIG["trend-reentry:risk05"]["riskFraction"],.005)

    def test_mtf_adx_original_clock_and_spot_gates(self):
        cfg=s.ARM_CONFIG["trend-reentry:control"]
        m=market();p=source();z=sig()
        self.assertIsNone(s.gate(z,m,p,NOW,cfg))
        self.assertEqual(s.gate(z,market(adx=21),p,NOW,cfg),"mtf-adx-not-confirmed")
        self.assertIsNone(s.gate(z,market(adx=21),p,NOW,
            s.ARM_CONFIG["trend-reentry:adx20"]))
        self.assertEqual(s.gate(z,{**m,"analysisBarAt":NOW-40*s.MINUTE},
            p,NOW,cfg),"prior-main-signal-age")
        self.assertIsNone(s.gate(z,{**m,"analysisBarAt":NOW-30*s.MINUTE},
            p,NOW,s.ARM_CONFIG["trend-reentry:age25"]))
        self.assertEqual(s.gate(z,m,source(107.),NOW,cfg),"original-spot-not-aligned")
        self.assertEqual(s.gate(z,{**m,"dataAt":SOURCE-60000},p,NOW,cfg),
            "original-spot-not-aligned")
        self.assertEqual(s.gate(z,{**m,"direction":"SHORT"},p,NOW,cfg),
            "main-opposes-study")
        self.assertEqual(s.gate(z,m,source(at=NOW+1000),NOW,cfg),
            "original-spot-not-aligned")


    def test_independent_original_5m_short_with_expired_main_signal(self):
        # Only the additional paper research arm may inspect a new 5m setup
        # when the old main 15m signal is no longer within its own age gate.
        m=market(direction="NEUTRAL",spot=103.)
        m["analysisBarAt"]=NOW-50*s.MINUTE
        m["trendContext"].update(direction="SHORT",intact=True)
        m["dmi"]["frames"]["15m"].update(
            direction="SHORT",barAt=(NOW//(15*s.MINUTE))*(15*s.MINUTE)-15*s.MINUTE)
        m["dmi"]["frames"]["1h"].update(
            direction="SHORT",barAt=(NOW//(60*s.MINUTE))*(60*s.MINUTE)-60*s.MINUTE)
        m["analysisSnapshot"].update(e20=99.,e50=106.)
        z=sig(side="SHORT")
        control=s.ARM_CONFIG["trend-reentry:control"]
        independent=s.ARM_CONFIG["trend-reentry:closed5m-independent"]
        self.assertEqual(s.gate(z,m,source(),NOW,control),
                         "prior-main-signal-age")
        self.assertIsNone(s.gate(z,m,source(),NOW,independent))
        plan,block=s.candidate(z,source(),independent)
        self.assertIsNone(block)
        self.assertEqual(plan["direction"],"SHORT")
        self.assertFalse(plan["realOrders"])
        self.assertFalse(plan["productReturnVerified"])
        self.assertGreaterEqual(plan["rr"],1.5)

        def blocked(change,code):
            sample=copy.deepcopy(m)
            sigcopy=copy.deepcopy(z)
            price=source()
            change(sample,sigcopy,price)
            self.assertEqual(s.gate(sigcopy,sample,price,NOW,independent),code)

        blocked(lambda m,z,p: z.update(closedAt=NOW-91000),
                "independent-closed5m-not-fresh")
        blocked(lambda m,z,p: m["dmi"]["frames"]["15m"].update(
                    barAt=NOW-90*s.MINUTE),
                "independent-mtf-source-not-fresh")
        blocked(lambda m,z,p: m["dmi"]["frames"]["1h"].update(
                    barAt=NOW-5*60*s.MINUTE),
                "independent-mtf-source-not-fresh")
        blocked(lambda m,z,p: m["dmi"]["frames"]["1h"].pop("barAt"),
                "independent-mtf-source-not-fresh")
        blocked(lambda m,z,p: p.update(at=NOW+1000),
                "original-spot-not-aligned")
        blocked(lambda m,z,p: m["dmi"]["frames"]["15m"].update(
                    direction="LONG"),
                "mtf-adx-not-confirmed")
        blocked(lambda m,z,p: m.update(direction="LONG"),
                "main-opposes-study")
        blocked(lambda m,z,p: m["trendContext"].update(direction="LONG"),
                "mtf-adx-not-confirmed")

    def test_only_new_study_books_new_short_when_main_age_expired(self):
        # Synthetic future observation, no retrospective backfill or order.
        original=s.seed(NOW-1000)
        preserved=copy.deepcopy(original)
        m=market(direction="NEUTRAL",spot=103.)
        m["analysisBarAt"]=NOW-50*s.MINUTE
        m["trendContext"].update(direction="SHORT",intact=True)
        m["dmi"]["frames"]["15m"].update(
            direction="SHORT",barAt=(NOW//(15*s.MINUTE))*(15*s.MINUTE)-15*s.MINUTE)
        m["dmi"]["frames"]["1h"].update(
            direction="SHORT",barAt=(NOW//(60*s.MINUTE))*(60*s.MINUTE)-60*s.MINUTE)
        m["analysisSnapshot"].update(e20=99.,e50=106.)
        signals={"trend-reentry":sig(side="SHORT"),
                 "breakout-retest":None,"false-breakout":None}
        with (patch.object(candles,"minute_history",return_value=([{}]*120,None)),
              patch.object(candles,"source",return_value=source()),
              patch.object(s,"signals",return_value=(signals,None))):
            result=s.advance(original,{},m,NOW)
        self.assertEqual(original,preserved)
        self.assertEqual(result["arms"]["trend-reentry:control"]["started"],0)
        self.assertEqual(result["arms"]["trend-reentry:control"]["lastBlock"],
                         "prior-main-signal-age")
        arm=result["arms"]["trend-reentry:closed5m-independent"]
        self.assertEqual(arm["started"],1)
        self.assertEqual(arm["position"]["direction"],"SHORT")
        self.assertFalse(arm["position"]["realOrders"])
        self.assertFalse(arm["position"]["productReturnVerified"])
        report=s.report(type("DB",(),{
            "execute":lambda self,*args:self,
            "fetchone":lambda self:(result,)})())
        brief=__import__("bob_diagnostics").short_regime_brief(report)
        names=[v["name"] for v in brief["variants"]]
        self.assertIn("trend-reentry:closed5m-independent",names)
        self.assertEqual(brief["configurationsReported"],66)

    def test_target_room_is_not_replaced_by_an_idealized_rr(self):
        p=source()
        z={**sig(),"targetAnchor":105.}
        self.assertEqual(s.candidate(z,p,s.ARM_CONFIG["trend-reentry:control"])[1],
            "target-room-insufficient")
        z={**sig(),"targetAnchor":107.}
        self.assertIsNone(s.candidate(z,p,s.ARM_CONFIG["trend-reentry:control"])[1])
        self.assertEqual(s.candidate(z,p,s.ARM_CONFIG["trend-reentry:rr20"])[1],
            None)  # exactly 2R
        z["targetAnchor"]=106.5
        self.assertEqual(s.candidate(z,p,s.ARM_CONFIG["trend-reentry:rr20"])[1],
            "target-room-insufficient")

    def test_migrates_independently_and_books_only_new_observed_prices(self):
        data={"history":{"bars_by_tf":{"1m":[]}}}
        old=s.seed(NOW-1000)
        # Already closed source bars and a fresh source quote are supplied by
        # the bounded existing intraday helper, not by a fabricated fill.
        signals={"trend-reentry":sig(),
                 "breakout-retest":None,"false-breakout":None}
        snap=copy.deepcopy(old)
        with (patch.object(candles,"minute_history",return_value=([{}]*120,None)), 
             patch.object(candles,"source",return_value=source()), 
             patch.object(s,"signals",return_value=(signals,None))):
            current=s.advance(old,data,market(),NOW)
        self.assertEqual(old,snap)
        self.assertEqual(current["arms"]["trend-reentry:control"]["started"],1)
        self.assertEqual(current["arms"]["trend-reentry:risk05"]["started"],1)
        self.assertIsNone(current["arms"]["breakout-retest:control"]["position"])
        self.assertEqual(current["arms"]["trend-reentry:control"]["levers"]["10"]["equityEur"],1000.)
        self.assertFalse(current["arms"]["trend-reentry:control"]["position"]["realOrders"])
        with (patch.object(candles,"minute_history",return_value=([{}]*120,None)), 
             patch.object(candles,"source",return_value=source(108.,SOURCE+30000)), 
             patch.object(s,"signals",return_value=(signals,None))):
            done=s.advance(current,data,market(now=NOW+30000,spot=108.),NOW+30000)
        base=done["arms"]["trend-reentry:control"]
        cautious=done["arms"]["trend-reentry:risk05"]
        self.assertEqual(base["closed"],1)
        self.assertEqual(base["exitCounts"]["target"],1)
        self.assertIsNone(base["position"])
        self.assertEqual(base["levers"]["10"]["completed"],1)
        self.assertGreater(base["levers"]["10"]["equityEur"],1000.)
        self.assertLess(cautious["levers"]["10"]["equityEur"],
                        base["levers"]["10"]["equityEur"])
        self.assertEqual(done["arms"]["breakout-retest:control"]["levers"]["10"]["completed"],0)

    def test_gap_never_books_model_profit(self):
        data={}
        signs={"trend-reentry":sig(),"breakout-retest":None,"false-breakout":None}
        with (patch.object(candles,"minute_history",return_value=([{}]*120,None)), 
             patch.object(candles,"source",return_value=source()), 
             patch.object(s,"signals",return_value=(signs,None))):
            first=s.advance(s.seed(NOW),data,market(),NOW)
        with (patch.object(candles,"minute_history",return_value=([{}]*120,None)), 
             patch.object(candles,"source",return_value=source(200.,SOURCE+120000)), 
             patch.object(s,"signals",return_value=(signs,None))):
            gap=s.advance(first,data,market(now=NOW+120000,spot=200.),NOW+120000)
        arm=gap["arms"]["trend-reentry:control"]
        self.assertEqual(arm["inconclusive"],1)
        self.assertEqual(arm["levers"]["10"]["equityEur"],1000.)
        self.assertEqual(arm["levers"]["10"]["completed"],0)

    def test_close_gate_only_original_spot_and_no_broker(self):
        state=s.seed(NOW)
        class DB:
            def execute(self,*args):return self
            def fetchone(self):return (state,)
        d=s.report(DB())
        self.assertEqual(len(d["variants"]),22)
        self.assertEqual(d["configurationsReported"],66)
        self.assertFalse(d["realOrders"])
        self.assertFalse(d["productReturnVerified"])
        self.assertFalse(d["strategyWinnerConfirmed"])
        report=__import__("bob_diagnostics").short_regime_brief(d)
        self.assertEqual(len(report["variants"]),22)
        self.assertEqual(report["configurationsReported"],66)
        self.assertNotIn("position",json.dumps(report))
        self.assertFalse(report["productReturnVerified"])

if __name__=="__main__": unittest.main()
