"""Prospective issuer-quote KO-band models: proof gate, stop and unknown sale."""
import copy
import json
import unittest
from datetime import datetime,timezone
from unittest.mock import patch

import gold_ko_distance_cohorts as s
import paper_simulation
import paper_ko_guard
import stop_target_audit

NOW=int(datetime(2026,11,19,15,30,tzinfo=timezone.utc).timestamp()*1000)


def market(now=NOW,spot=3700):
    return dict(direction="LONG",ready=True,priceFresh=True,price=spot,
      dataAt=now-1000,atr=10,analysisBarAt=NOW-5*60000,
      session=dict(entryAllowed=True),plan=dict(kind="candidate",unit="USD/oz",
      direction="LONG",entry=spot,stop=spot-10,target=spot+30))


def documents():
    options=[]
    quotes={}
    for symbol,distance in [("DE000AAAAAAA",2.6),("DE000BBBBBBB",4.5),("DE000CCCCCCC",8.)]:
        options.append(dict(isin=symbol,scope="XAU/USD",direction="LONG"))
        quotes[symbol]=dict(isin=symbol,currency="EUR",bid=9.9,ask=10.,
             bidAt=NOW-1000,askAt=NOW-1000,
             priceKind="market-observation",leverageObservation=dict(
                 current=True,value=10.),koDistance=distance)
    return dict(choices=options),quotes


def q(raw,now,isin):
    return raw if raw and raw.get("currency")=="EUR" and raw.get("ask") else None


def er(choice,raw,market,now):
    return (None,dict(distancePct=raw["koDistance"],danger=False,
                      crossed=False,protectiveDistancePct=1.5))


def gr(pos,raw,market,now):
    return dict(distancePct=raw.get("koDistance",4),danger=False,
                crossed=False,protectiveDistancePct=1.5),None


class KoDistanceTest(unittest.TestCase):
    def _patch(self):
        return (patch.object(paper_simulation,"fresh_quote",side_effect=q),
                patch.object(paper_ko_guard,"entry_reason",side_effect=er),
                patch.object(paper_ko_guard,"assess",side_effect=gr),
                patch.object(paper_ko_guard,"terminal",return_value=None),
                patch.object(stop_target_audit,"valid_plan",return_value=True))

    def test_three_tiers_keep_exact_original_quotes_and_independent_cash(self):
        selection,quotes=documents()
        original=copy.deepcopy(quotes)
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            result=s.advance(s.seed(NOW-1000),market(),selection,quotes,NOW)
        self.assertEqual(quotes,original)
        self.assertEqual(result["eligiblePricePairs"],3)
        self.assertEqual(set(result["arms"]),set(s.BANDS))
        for tier in s.BANDS:
            arm=result["arms"][tier];self.assertEqual(arm["started"],1)
            self.assertIsNotNone(arm["position"])
            self.assertEqual(arm["position"]["realOrders"],False)
            self.assertEqual(arm["position"]["brokerExecutionVerified"],False)
            self.assertIsNone(arm["equityEur"]) # cannot mark without later dated bid
        self.assertEqual(result["arms"][s.BANDS[0]]["position"]["isin"],"DE000AAAAAAA")
        self.assertEqual(result["arms"][s.BANDS[1]]["position"]["isin"],"DE000BBBBBBB")
        self.assertEqual(result["arms"][s.BANDS[2]]["position"]["isin"],"DE000CCCCCCC")
        self.assertEqual(result["arms"][s.BANDS[0]]["closed"],0)

    def test_later_dated_issuer_bid_can_settle_without_broker_claim(self):
        sel,quotes=documents()
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            entered=s.advance(s.seed(NOW),market(),sel,quotes,NOW)
        after=copy.deepcopy(quotes)
        for raw in after.values():
            raw["bid"]=11.2;raw["bidAt"]=NOW+30000;raw["askAt"]=NOW+30000
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            settled=s.advance(entered,market(NOW+30000,3731),sel,after,NOW+30000)
        for tier in s.BANDS:
            arm=settled["arms"][tier]
            self.assertEqual(arm["closed"],1)
            self.assertEqual(arm["modelWins"],1)
            self.assertGreater(arm["cashEur"],1000)
            self.assertEqual(arm["exitCounts"]["issuer-bid-observed"],1)
            self.assertIsNone(arm["position"])

    def test_unobserved_exit_never_earns_return_or_forges_fill(self):
        sel,quotes=documents()
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):first=s.advance(s.seed(NOW),market(),sel,quotes,NOW)
        blank={k:{**v,"bid":None} for k,v in quotes.items()}
        def blank_quote(raw,now,isin):return None
        a,b,c,d,e=self._patch()
        with (patch.object(paper_simulation,"fresh_quote",side_effect=blank_quote),b,c,d,e):
            paused=s.advance(first,market(NOW+30000,3732),sel,blank,NOW+30000)
        for tier in s.BANDS:
            arm=paused["arms"][tier]
            self.assertEqual(arm["closed"],0)
            self.assertTrue(arm["position"])
            self.assertIsNone(arm["equityEur"])
            self.assertEqual(arm["realizedModelNetEur"],0)
            self.assertGreater(arm["missingExitBid"],0)

    def test_no_issuer_quote_leverage_or_date_no_entry(self):
        selection,quotes=documents()
        selection["choices"]=selection["choices"][:1]
        bad=copy.deepcopy(quotes)
        bad["DE000AAAAAAA"]["leverageObservation"]["current"]=False
        bad["DE000AAAAAAA"]["leverageCalculation"]={}
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            out=s.advance(s.seed(NOW),market(),selection,bad,NOW)
        self.assertEqual(out["eligiblePricePairs"],0)
        self.assertTrue(all(a["started"]==0 for a in out["arms"].values()))
        bad["DE000AAAAAAA"]["leverageObservation"]["current"]=True
        bad["DE000AAAAAAA"]["currency"]="CHF"
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            out=s.advance(s.seed(NOW),market(),selection,bad,NOW)
        self.assertEqual(out["eligiblePricePairs"],0)
        bad["DE000AAAAAAA"]["currency"]="EUR"
        selection["choices"][0]["issuerVenue"]="Swiss DOTS (CHF)"
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            out=s.advance(s.seed(NOW),market(),selection,bad,NOW)
        self.assertEqual(out["eligiblePricePairs"],0)

    def test_converted_chf_quote_never_enters_original_eur_ko_cohorts(self):
        selection, quotes = documents()
        before=copy.deepcopy(quotes)
        def projected_chf(raw,now,isin):
            # Native CHF quote projected to EUR by existing generic paper
            # adapter; the new EUR-only KO study must reject it even when
            # Swiss DOTS venue data are absent from the original metadata.
            return {"isin":isin,"bid":9.9,"ask":10.,"currency":"EUR",
                "bidAt":now,"askAt":now,"source":"Issuer market",
                "paperFxConversion":{"at":now},
                "paperNativeQuote":{"currency":"CHF","bid":10.4,"ask":10.6}}
        a,b,c,d,e=self._patch()
        with (patch.object(paper_simulation,"fresh_quote",side_effect=projected_chf),
              b,c,d,e):
            state=s.advance(s.seed(NOW),market(),selection,quotes,NOW)
        self.assertEqual(state["eligiblePricePairs"],0)
        self.assertEqual(quotes,before)
        for tier in s.BANDS:
            arm=state["arms"][tier]
            self.assertEqual(arm["started"],0)
            self.assertIsNone(arm["position"])
            self.assertEqual(arm["cashEur"],1000.)
        # An apparently EUR quote coming from an inadmissible Swiss source
        # is also blocked even without conversion markers.
        def swiss_source(raw,now,isin):
            return {"isin":isin,"bid":9.9,"ask":10.,"currency":"EUR",
                "bidAt":now,"askAt":now,"source":"Swissquote Swiss DOTS"}
        a,b,c,d,e=self._patch()
        with (patch.object(paper_simulation,"fresh_quote",side_effect=swiss_source),
              b,c,d,e):
            second=s.advance(s.seed(NOW),market(),selection,quotes,NOW)
        self.assertEqual(second["eligiblePricePairs"],0)
        self.assertTrue(all(a["started"]==0 for a in second["arms"].values()))

    def test_report_never_exposes_isins_quotes_or_executable_order(self):
        sel,quotes=documents()
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            state=s.advance(s.seed(NOW),market(),sel,quotes,NOW)
        class Conn:
            def execute(self,*args):return self
            def fetchone(self):return (state,)
        result=s.report(Conn())
        compact=__import__("bob_diagnostics").ko_distance_brief(result)
        self.assertEqual(len(compact["arms"]),3)
        # 2026 timestamps are in Unix milliseconds (~1.8e12), not bounded
        # research counters (<1e9). Never mislabel an active worker as stale.
        self.assertEqual(compact["checkedAt"],NOW)
        self.assertEqual(compact["originalQuoteChecks"],1)
        self.assertFalse(compact["brokerExecutionVerified"])
        self.assertFalse(compact["realOrders"])
        self.assertFalse(compact["productReturnVerified"])
        self.assertNotIn("DE000",json.dumps(compact))
        self.assertNotIn("entryAsk",json.dumps(compact))
        self.assertNotIn('"position":',json.dumps(compact))

    def test_neutral_direction_and_invalid_plan_not_mislabeled_as_missing_quote(self):
        selection,quotes=documents()
        neutral=market()
        neutral["direction"]="NEUTRAL"
        a,b,c,d,e=self._patch()
        with (a,b,c,d,e):
            state=s.advance(s.seed(NOW),neutral,selection,quotes,NOW)
        self.assertTrue(all(x["lastBlock"]=="no-confirmed-market-direction"
                            and x["started"]==0 for x in state["arms"].values()))
        compact=__import__("bob_diagnostics").ko_distance_brief(s.report(type(
            "Conn",(),{"execute":lambda self,*args:self,
                       "fetchone":lambda self:(state,)})()))
        self.assertTrue(all(x["lastBlock"]=="no-confirmed-market-direction"
                            for x in compact["arms"]))
        planned=market()
        planned["plan"]=None
        a,b,c,d,_=self._patch()
        with (a,b,c,d,patch.object(stop_target_audit,"valid_plan",return_value=False)):
            state=s.advance(s.seed(NOW),planned,selection,quotes,NOW)
        self.assertTrue(all(x["lastBlock"]=="no-verified-stop-target-plan"
                            and x["started"]==0 for x in state["arms"].values()))
        self.assertEqual(state["eligiblePricePairs"],0)


    def test_invalid_clock_is_unknown_without_leaking_arbitrary_payload(self):
        import bob_diagnostics
        state={"status":"collecting","checkedAt":float("nan"),
               "originalQuoteChecks":411,"eligiblePricePairs":0,
               "arms":[{"koTier":t,"started":0,"closed":0,
                        "positionOpen":False,"missingExitBid":0,
                        "unresolvedKo":0,"lastBlock":"no-timestamped-issuer-ko-pair",
                        "modelCashEur":1000.,"modelEquityEur":1000.,
                        "modelRealizedEur":0.} for t in s.BANDS]}
        out=bob_diagnostics.ko_distance_brief(state)
        self.assertIsNone(out["checkedAt"])
        self.assertEqual(out["originalQuoteChecks"],411)
        self.assertEqual(len(out["arms"]),3)
        json.dumps(out,allow_nan=False)
        state["checkedAt"]=NOW
        self.assertEqual(bob_diagnostics.ko_distance_brief(state)["checkedAt"],NOW)


if __name__=="__main__":unittest.main()
