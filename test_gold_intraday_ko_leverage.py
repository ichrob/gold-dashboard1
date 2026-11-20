"""Regression tests for independent, issuer-backed KO and leverage PAPER arms."""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import gold_intraday_ko_leverage as study
import gold_ko_distance_cohorts as cohort
import paper_simulation
import paper_ko_guard
import stop_target_audit

NOW=int(datetime(2026,11,20,15,30,tzinfo=timezone.utc).timestamp()*1000)
BAND="medium-3-to-6"


def fixture(*, side="LONG", leverages=(5.,10.,20.)):
    sign=1 if side=="LONG" else -1
    price=3700.
    m=dict(direction=side,ready=True,priceFresh=True,price=price,
        dataAt=NOW-1000,atr=10.,analysisBarAt=NOW-300000,
        entryTimingGate=dict(allowed=True),session=dict(entryAllowed=True),
        plan=dict(kind="candidate",unit="USD/oz",direction=side,
                  entry=price,stop=price-sign*15.,target=price+sign*120.))
    choices=[];quotes={}
    for index,leverage in enumerate(leverages):
        isin="DE000TEST%03d" % (index+1)
        choices.append(dict(isin=isin,scope="XAU/USD",direction=side))
        quotes[isin]=dict(isin=isin,currency="EUR",bid=9.9,ask=10.,
            bidAt=NOW-1000,askAt=NOW-1000,
            leverageObservation=dict(current=True,value=leverage),
            koDistance=4.5,barrierUsd=price-sign*166.5,
            priceKind="market-observation")
    return m,dict(choices=choices,researchCandidates=copy.deepcopy(choices)),quotes


def fresh_quote(raw,now,isin):
    if raw and raw.get("currency")=="EUR" and raw.get("ask"):
        return raw
    return None


def entry_reason(choice,raw,market,now):
    return None,dict(barrierUsd=raw["barrierUsd"],distancePct=raw["koDistance"],
        protectiveDistancePct=1.5,danger=False,crossed=False)


def assess(position,raw,market,now):
    if not raw:return None,"missing"
    return dict(barrierUsd=raw["barrierUsd"],distancePct=raw["koDistance"],
        protectiveDistancePct=1.5,danger=False,crossed=False),None


class IntradayKoLeverageTest(unittest.TestCase):
    def _patch(self):
        return (
            patch.object(paper_simulation,"fresh_quote",side_effect=fresh_quote),
            patch.object(paper_ko_guard,"entry_reason",side_effect=entry_reason),
            patch.object(paper_ko_guard,"assess",side_effect=assess),
            patch.object(paper_ko_guard,"terminal",return_value=None),
            patch.object(stop_target_audit,"valid_plan",return_value=True),
        )

    def test_higher_verified_leverage_is_selected_at_safe_ko_distance(self):
        market,selection,quotes=fixture()
        original=copy.deepcopy(quotes)
        with self._patch()[0],self._patch()[1],self._patch()[2],self._patch()[3],self._patch()[4]:
            state=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        self.assertEqual(quotes,original)
        c=state["policies"]["balanced"]["arms"][BAND]
        h=state["policies"]["high-safe"]["arms"][BAND]
        self.assertEqual(c["position"]["leverage"],5.)
        self.assertEqual(h["position"]["leverage"],20.)
        for arm in (c,h):
            p=arm["position"]
            self.assertLessEqual(p["entryDebit"],study.KO_MAX_LOSS_FRACTION*cohort.CAPITAL)
            self.assertFalse(p["realOrders"])
            self.assertFalse(p["brokerExecutionVerified"])
            self.assertLessEqual(p["entryDebit"],arm["cashEur"]+p["entryDebit"])
        self.assertEqual(state["policies"]["high-safe"]["eligiblePricePairs"],1)
        self.assertEqual(state["policies"]["balanced"]["eligiblePricePairs"],1)

    def test_ko_too_close_to_stop_rejects_high_leverage_even_if_marked_safe(self):
        market,selection,quotes=fixture()
        last=selection["choices"][-1]["isin"]
        quotes[last]["barrierUsd"]=market["plan"]["stop"]-1.
        # Guard's coarse distance estimate cannot substitute its exact barrier.
        with self._patch()[0],self._patch()[1],self._patch()[2],self._patch()[3],self._patch()[4]:
            state=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        high=state["policies"]["high-safe"]["arms"][BAND]["position"]
        self.assertIsNotNone(high)
        self.assertEqual(high["leverage"],10.)

    def test_no_entry_if_missing_gate_quotes_or_excessive_leverage(self):
        market,selection,quotes=fixture(leverages=(45.,))
        with self._patch()[0],self._patch()[1],self._patch()[2],self._patch()[3],self._patch()[4]:
            s=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        self.assertEqual(sum(x["started"] for a in s["policies"].values()
                             for x in a["arms"].values()),0)
        market,selection,quotes=fixture()
        market["entryTimingGate"]=dict(allowed=False)
        with self._patch()[0],self._patch()[1],self._patch()[2],self._patch()[3],self._patch()[4]:
            s=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        self.assertEqual(sum(x["started"] for a in s["policies"].values()
                             for x in a["arms"].values()),0)
        market["entryTimingGate"]=None
        with self._patch()[0],self._patch()[1],self._patch()[2],self._patch()[3],self._patch()[4]:
            s=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        self.assertEqual(sum(x["started"] for a in s["policies"].values()
                             for x in a["arms"].values()),0)

    def test_stop_only_tightens_and_reversal_uses_a_later_issuer_bid(self):
        for side in ("LONG","SHORT"):
            with self.subTest(side=side):
                market,selection,quotes=fixture(side=side)
                p1,p2,p3,p4,p5=self._patch()
                with p1,p2,p3,p4,p5:
                    original=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
                first=original["policies"]["high-safe"]["arms"][BAND]["position"]
                self.assertIsNotNone(first)
                before=first["stop"]
                sign=1 if side=="LONG" else -1
                later=NOW+60000
                for quote in quotes.values():
                    quote["bidAt"]=later-1000;quote["askAt"]=later-1000
                market["dataAt"]=later-1000;market["price"]=3700.+sign*40
                market["plan"]["entry"]=market["price"]
                # An active position is monitored even when no fresh entry setup.
                market["entryTimingGate"]=dict(allowed=False)
                p1,p2,p3,p4,p5=self._patch()
                with p1,p2,p3,p4,p5:
                    trailing=study.advance(original,market,selection,quotes,later)
                active=trailing["policies"]["high-safe"]["arms"][BAND]["position"]
                self.assertGreater(sign*(active["stop"]-before),0)
                self.assertGreater(active["trailingStopUpdates"],0)
                market["direction"]="SHORT" if side=="LONG" else "LONG"
                market["dataAt"]=later+30000-1000
                market["price"]=3700.+sign*35
                for quote in quotes.values():
                    quote["bidAt"]=later+30000-1000
                    quote["askAt"]=later+30000-1000
                p1,p2,p3,p4,p5=self._patch()
                with p1,p2,p3,p4,p5:
                    exited=study.advance(trailing,market,selection,quotes,later+30000)
                arm=exited["policies"]["high-safe"]["arms"][BAND]
                self.assertEqual(arm["closed"],1)
                self.assertIsNone(arm["position"])
                self.assertEqual(arm["exitCounts"]["issuer-bid-observed"],1)
                self.assertFalse(exited["realOrders"])

    def test_target_profit_model_must_cover_spread_and_fees(self):
        market,selection,quotes=fixture()
        for q in quotes.values():q["bid"]=.1
        p1,p2,p3,p4,p5=self._patch()
        with p1,p2,p3,p4,p5:
            state=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        self.assertTrue(all(a["started"]==0 for p in state["policies"].values()
                            for a in p["arms"].values()))

    def test_report_never_shows_isin_or_order_authorization(self):
        market,selection,quotes=fixture()
        p1,p2,p3,p4,p5=self._patch()
        with p1,p2,p3,p4,p5:
            state=study.advance(study.seed(NOW-1000),market,selection,quotes,NOW)
        class Conn:
            def execute(self,*args):return self
            def fetchone(self):return (state,)
        report=study.report(Conn())
        self.assertEqual(report["armCount"],6)
        self.assertFalse(report["realOrders"])
        self.assertFalse(report["productReturnVerified"])
        import json
        self.assertNotIn("DE000",json.dumps(report))
        self.assertNotIn("entryAsk",json.dumps(report))


if __name__=="__main__":
    unittest.main()
