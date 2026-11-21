"""Mirrored prospective LONG/SHORT original-5m paper research regressions.

These are synthetic, controlled fixtures: never broker fills or a claim
about historical Gold profitability. Old 22 accounts must stay untouched.
"""
import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import gold_short_scenarios as s
import intraday_timing_study as candles
from test_gold_short_scenarios import market, sig, source, NOW, SOURCE

PAIR = ("trend-reentry:closed5m-long", "trend-reentry:closed5m-short")
BIDIRECTIONAL = "trend-reentry:closed5m-independent"
LEGACY = "trend-reentry:control"


def context(side):
    m = market(direction="NEUTRAL", spot=103.)
    m["analysisBarAt"] = NOW - 50*s.MINUTE
    m["trendContext"].update(direction=side, intact=True, available=True)
    m["dmi"]["frames"]["15m"].update(
        direction=side,
        barAt=NOW//(15*s.MINUTE)*(15*s.MINUTE)-15*s.MINUTE)
    m["dmi"]["frames"]["1h"].update(
        direction=side,
        barAt=NOW//(60*s.MINUTE)*(60*s.MINUTE)-60*s.MINUTE)
    m["analysisSnapshot"].update(
        e20=106. if side=="LONG" else 99.,
        e50=100. if side=="LONG" else 106.)
    return m


def mirrored_bars(side):
    """Same dimensionless volatility/shape reflected around XAU=103."""
    closes_at = NOW-15000
    bars = []
    for i in range(18):
        op=112. - i*.5
        cl=op-.2
        raw=dict(open=op,close=cl,high=op+1.,low=cl-1.)
        bars.append(raw)
    bars[-3].update(open=100.5,close=102.,high=102.2,low=100.3)
    bars[-2].update(open=102.,close=101.,high=102.2,low=100.8)
    bars[-1].update(open=101.,close=103.,high=103.2,low=100.9)
    if side=="SHORT":
        for bar in bars:
            lo,hi=bar["low"],bar["high"]
            bar.update(open=206.-bar["open"],close=206.-bar["close"],
                       high=206.-lo,low=206.-hi)
    for i,bar in enumerate(bars):
        bar["openTime"]=closes_at-(18-i)*5*s.MINUTE
        bar["closeTime"]=bar["openTime"]+5*s.MINUTE
        bar["estimated"]=False
    return bars


def signal_from_original_5m(side):
    # Isolate the exact closed-bar signal parser, not the provider network.
    rows=[{"estimated":False} for _ in range(120)]
    with patch.object(candles,"aggregate",return_value=mirrored_bars(side)):
        signals,error=s.signals(rows,NOW)
    assert error is None, error
    return signals["trend-reentry"]


def step(state,side,now,price,at,signals):
    m=context(side)
    m.update(price=price,dataAt=at)
    with (patch.object(candles,"minute_history",
                       return_value=([{"estimated":False}]*120,None)),
          patch.object(candles,"source",
                       return_value=dict(available=True,estimated=False,
                                         at=at,price=price)),
          patch.object(s,"signals",
                       return_value=({"trend-reentry":signals,
                                      "breakout-retest":None,
                                      "false-breakout":None},None))):
        return s.advance(state,{},m,now)


class MatchedLongShortStudy(unittest.TestCase):
    def test_exact_same_thresholds_and_separate_seed_dates(self):
        old=s.ARM_CONFIG[BIDIRECTIONAL]
        for side,name in zip(("LONG","SHORT"),PAIR):
            cfg=s.ARM_CONFIG[name]
            self.assertEqual(cfg["studySide"],side)
            self.assertEqual(
                {key:value for key,value in cfg.items()
                 if key not in ("option","studySide")},
                {key:value for key,value in old.items() if key!="option"})
        initial=s.seed(NOW)
        self.assertEqual(len(initial["arms"]),24)
        self.assertEqual(initial["arms"][PAIR[0]]["studyStartedAt"],NOW)
        self.assertEqual(initial["arms"][PAIR[1]]["studyStartedAt"],NOW)
        self.assertNotIn("studyStartedAt",initial["arms"][LEGACY])
        self.assertFalse(initial["realOrders"])

    def test_original_closed_5m_signal_is_symmetric(self):
        for side in ("LONG","SHORT"):
            with self.subTest(side=side):
                z=signal_from_original_5m(side)
                self.assertEqual(z["direction"],side)
                self.assertEqual(z["kind"],"trend-reentry")
                self.assertEqual(z["closedAt"],NOW-15000)
                self.assertTrue(s.gate(z,context(side),source(),NOW,
                            s.ARM_CONFIG["trend-reentry:closed5m-"+side.lower()]) is None)
                plan,code=s.candidate(z,source(),
                            s.ARM_CONFIG["trend-reentry:closed5m-"+side.lower()])
                self.assertIsNone(code)
                self.assertGreaterEqual(plan["rr"],1.5)
                if side=="LONG":
                    self.assertLess(plan["stop"],103.)
                    self.assertGreater(plan["target"],103.)
                else:
                    self.assertGreater(plan["stop"],103.)
                    self.assertLess(plan["target"],103.)
                self.assertFalse(plan["realOrders"])
                self.assertFalse(plan["productReturnVerified"])

    def test_prospective_independent_entries_exits_and_migration_both_sides(self):
        for side in ("LONG","SHORT"):
            with self.subTest(side=side):
                state=s.seed(NOW-5*s.MINUTE)
                # Emulate already-running 22-arm production state. New pair
                # must start empty from first real forward worker evaluation.
                for name in PAIR:
                    del state["arms"][name]
                frozen=copy.deepcopy(state)
                z=sig(side=side)
                opened=step(state,side,NOW,103.,SOURCE,z)
                self.assertEqual(state,frozen)
                own="trend-reentry:closed5m-"+side.lower()
                opposite="trend-reentry:closed5m-"+(
                    "short" if side=="LONG" else "long")
                self.assertEqual(opened["arms"][LEGACY]["started"],0)
                self.assertEqual(opened["arms"][LEGACY]["lastBlock"],
                                 "prior-main-signal-age")
                self.assertEqual(opened["arms"][own]["started"],1)
                self.assertEqual(opened["arms"][opposite]["started"],0)
                self.assertEqual(opened["arms"][opposite]["lastBlock"],
                                 "study-side-mismatch")
                self.assertEqual(opened["arms"][own]["studyStartedAt"],NOW)
                self.assertEqual(opened["arms"][opposite]["studyStartedAt"],NOW)
                self.assertEqual(opened["arms"][BIDIRECTIONAL]["started"],1)
                p=opened["arms"][own]["position"]
                self.assertEqual(p["direction"],side)
                self.assertEqual(p["entry"],103.)
                self.assertTrue(
                    (p["stop"]<103.<p["target"]) if side=="LONG"
                    else (p["target"]<103.<p["stop"]))
                self.assertFalse(p["realOrders"])
                self.assertFalse(p["productReturnVerified"])
                self.assertEqual(opened["arms"][own]["levers"]["10"]["equityEur"],
                                 1000.)
                # Exit ONLY at a newer real observed source timestamp. A test
                # crossing the target models a fill at the observed spot.
                hit=110. if side=="LONG" else 96.
                done=step(opened,side,NOW+30000,hit,SOURCE+30000,z)
                arm=done["arms"][own]
                self.assertEqual(arm["closed"],1)
                self.assertEqual(arm["exitCounts"]["target"],1)
                self.assertIsNone(arm["position"])
                self.assertGreater(arm["levers"]["10"]["equityEur"],1000.)
                self.assertEqual(done["arms"][opposite]["closed"],0)
                self.assertEqual(done["arms"][LEGACY]["closed"],0)

                class DB:
                    def execute(self,*args):return self
                    def fetchone(self):return (done,)
                report=s.report(DB())
                view=__import__("bob_diagnostics").short_regime_brief(report)
                self.assertEqual(len(report["variants"]),24)
                self.assertEqual(len(view["variants"]),24)
                self.assertEqual(view["configurationsReported"],72)
                pair={r["name"]:r for r in view["variants"] if r["name"] in PAIR}
                self.assertEqual(pair[own]["studySide"],side)
                self.assertEqual(pair[own]["studyStartedAt"],NOW)
                self.assertEqual(pair[own]["modeled10xClosed"],1)
                self.assertEqual(pair[opposite]["modeled10xClosed"],0)
                self.assertNotIn('"position"',json.dumps(view))
                self.assertFalse(view["realOrders"])
                self.assertFalse(view["productReturnVerified"])

    def test_both_sides_reject_unconfirmed_or_stale_sources_and_bad_risk(self):
        for side in ("LONG","SHORT"):
            with self.subTest(side=side):
                name="trend-reentry:closed5m-"+side.lower()
                cfg=s.ARM_CONFIG[name]
                m=context(side)
                z=sig(side=side)
                good=source()
                self.assertIsNone(s.gate(z,m,good,NOW,cfg))
                opposite=dict(z,direction="SHORT" if side=="LONG" else "LONG")
                self.assertEqual(s.gate(opposite,m,good,NOW,cfg),
                                 "study-side-mismatch")
                stale=dict(z,closedAt=NOW-92000)
                self.assertEqual(s.gate(stale,m,good,NOW,cfg),
                                 "independent-closed5m-not-fresh")
                missing=copy.deepcopy(m)
                del missing["dmi"]["frames"]["15m"]["barAt"]
                self.assertEqual(s.gate(z,missing,good,NOW,cfg),
                                 "independent-mtf-source-not-fresh")
                opposed=copy.deepcopy(m)
                opposed["direction"]="SHORT" if side=="LONG" else "LONG"
                self.assertEqual(s.gate(z,opposed,good,NOW,cfg),
                                 "main-opposes-study")
                opposed=context(side)
                opposed["dmi"]["frames"]["1h"]["direction"]=(
                    "SHORT" if side=="LONG" else "LONG")
                self.assertEqual(s.gate(z,opposed,good,NOW,cfg),
                                 "mtf-adx-not-confirmed")
                closed=context(side)
                closed["session"]["entryAllowed"]=False
                self.assertEqual(s.gate(z,closed,good,NOW,cfg),
                                 "session-closed")
                invalid=copy.deepcopy(z)
                invalid["targetAnchor"]=103.+(1 if side=="LONG" else -1)
                self.assertEqual(s.candidate(invalid,good,cfg)[1],
                                 "target-room-insufficient")

    def test_no_model_profit_during_source_gap_in_either_direction(self):
        for side in ("LONG","SHORT"):
            opened=step(s.seed(NOW-30000),side,NOW,103.,SOURCE,
                        sig(side=side))
            before=copy.deepcopy(opened)
            later=step(opened,side,NOW+120000,
                       110. if side=="LONG" else 96.,
                       SOURCE+120000,sig(side=side))
            arm=later["arms"]["trend-reentry:closed5m-"+side.lower()]
            self.assertEqual(opened,before)
            self.assertEqual(arm["inconclusive"],1)
            self.assertEqual(arm["closed"],0)
            self.assertEqual(arm["levers"]["10"]["equityEur"],1000.)
            self.assertIsNone(arm["position"])


if __name__=="__main__":
    unittest.main()
