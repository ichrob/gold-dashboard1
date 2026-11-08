import unittest
from datetime import datetime, timezone, timedelta
import broker_bridge
import trade_execution_readiness as tr


NOW = datetime(2026, 11, 9, 14, 30, tzinfo=timezone.utc)


def fixture():
    at = (NOW - timedelta(seconds=20)).isoformat()
    signal = dict(direction="LONG", ready=True, priceFresh=True, at=at, marketOpen=True)
    product = dict(isin="DE000FG4JXV7", direction="LONG", underlying="XAU/USD",
        underlyingType="SPOT", productType="TURBO", factorProduct=False,
        currency="EUR", identityVerified=True, venueVerified=True,
        koVerified=True, termsVerified=True, tradingOpen=True,
        ko=3900, strike=3900, ratio=0.01, leverage=12,
        koDistancePct=10, bidEUR=9.8, askEUR=10.0,
        quoteAt=at, quoteSource="Issuer direct observed", quoteKind="ISSUER_BID_ASK")
    risk = dict(cashEUR=1000, positionBudgetEUR=200, maxLossEUR=200,
        dailyLossEUR=0, dailyLossLimitEUR=250, expectedFeesEUR=5,
        openPositions=0, maxPositions=1, stopProductBidEUR=9,
        targetProductBidEUR=12, stopTargetVerified=True)
    return signal, product, risk


class ExecutionReadinessTests(unittest.TestCase):
    def test_manual_review_only_for_complete_evidence(self):
        a,b,c=fixture()
        p=tr.build_review(a,b,c,now=NOW)
        self.assertEqual(p["state"],"MANUAL_REVIEW")
        self.assertEqual(p["quantity"],19)
        self.assertEqual(p["orderSide"],"BUY")  # SHORT turbo is also bought
        self.assertEqual(p["estimatedWorstCaseLossEUR"],195)
        self.assertFalse(p["tradeApproved"])
        self.assertFalse(p["orderSubmitted"])
        self.assertFalse(p["executionPriceConfirmed"])
        self.assertFalse(p["brokerBuyPermissionVerified"])
        self.assertEqual(len(p["reviewFingerprint"]),64)
        self.assertEqual(p["reviewFingerprint"],tr.build_review(a,b,c,now=NOW)["reviewFingerprint"])

    def test_missing_original_proofs_and_estimates_never_generate_order(self):
        for key,value in [
            ("identityVerified",False),("venueVerified",False),("koVerified",False),
            ("termsVerified",False),("tradingOpen",False),("quoteKind","CALCULATED"),
            ("quoteSource",""),("currency","CHF"),("underlyingType","FUTURE"),
            ("factorProduct",True),("koDistancePct",3),("isin","DE0000000000")
        ]:
            a,b,c=fixture()
            b[key]=value
            with self.subTest(key=key):
                p=tr.build_review(a,b,c,now=NOW)
                self.assertEqual(p["state"],"BLOCKED")
                self.assertEqual(p["quantity"],0)
                self.assertIsNone(p["limitPriceEUR"])

    def test_missing_or_stale_signal_and_quote_are_blocked(self):
        for case in ("signal_stale","signal_future","quote_stale","quote_naive","weekend","neutral"):
            a,b,c=fixture()
            if case=="signal_stale":a["at"]=(NOW-timedelta(seconds=61)).isoformat()
            if case=="signal_future":a["at"]=(NOW+timedelta(seconds=2)).isoformat()
            if case=="quote_stale":b["quoteAt"]=(NOW-timedelta(seconds=91)).isoformat()
            if case=="quote_naive":b["quoteAt"]="2026-11-09T14:30:00"
            if case=="weekend":a["marketOpen"]=False
            if case=="neutral":a["direction"]="ABWARTEN"
            with self.subTest(case=case):
                p=tr.build_review(a,b,c,now=NOW)
                self.assertEqual(p["state"],"BLOCKED")
                self.assertFalse(p["orderSubmitted"])

    def test_limits_and_broker_eligibility_never_imply_trade_permission(self):
        for case in ("loss_cap","open_position","no_fees","no_stop","missing_cash"):
            a,b,c=fixture()
            if case=="loss_cap":c["dailyLossEUR"]=250
            if case=="open_position":c["openPositions"]=1
            if case=="no_fees":c["expectedFeesEUR"]=None
            if case=="no_stop":c["stopTargetVerified"]=False
            if case=="missing_cash":c["cashEUR"]=None
            with self.subTest(case=case):
                self.assertEqual(tr.build_review(a,b,c,now=NOW)["state"],"BLOCKED")
        a,b,c=fixture()
        a["direction"]=b["direction"]="SHORT"
        p=tr.build_review(a,b,c,broker="ibkr",now=NOW)
        self.assertEqual(p["state"],"BROKER_API_NOT_CONNECTED")
        self.assertIsNone(p["orderSide"])
        self.assertEqual(p["quantity"],0)
        self.assertIn("Brokerspezifische Vertrags-ID",p["reasons"][0])
        self.assertFalse(p["tradeApproved"])
        self.assertFalse(broker_bridge.status()["executionEnabled"])

    def test_fee_reserved_from_cash_and_budget_and_clock_alignment(self):
        a,b,c=fixture()
        c["cashEUR"]=100
        p=tr.build_review(a,b,c,now=NOW)
        self.assertEqual(p["state"],"MANUAL_REVIEW")
        self.assertEqual(p["quantity"],9)
        self.assertLessEqual(p["estimatedWorstCaseLossEUR"],100)
        b["quoteAt"]=(NOW-timedelta(seconds=85)).isoformat()
        p=tr.build_review(a,b,c,now=NOW)
        self.assertEqual(p["state"],"BLOCKED")
        self.assertIn("Produktkurs und Handelssignal liegen zeitlich auseinander",p["reasons"])

    def test_bridge_returns_non_executable_four_stage_status(self):
        a,b,c=fixture()
        p=broker_bridge.prepare_order_review(a,b,c,now=NOW)
        self.assertEqual(p["state"],"MANUAL_REVIEW")
        ready=broker_bridge.status()["fourStageReadiness"]
        self.assertFalse(ready["realOrdersEnabled"])
        self.assertFalse(ready["canOpenOrders"])
        self.assertFalse(ready["canSellOrders"])
        self.assertIn("CONFIRMED_RECEIPT",ready["positionMonitoring"])

    def test_low_max_risk_is_full_ko_cash_exposure_not_stop_assumption(self):
        a,b,c=fixture()
        c["maxLossEUR"]=8
        result=tr.build_review(a,b,c,now=NOW)
        self.assertEqual(result["state"],"BLOCKED")
        self.assertEqual(result["quantity"],0)

    def test_never_dispatches_broker_order_or_exposes_secrets(self):
        a,b,c=fixture()
        p=tr.build_review(a,b,c,now=NOW)
        self.assertNotIn("password",p)
        self.assertNotIn("token",p)
        self.assertFalse(tr.pipeline_status()["realOrdersEnabled"])
        with self.assertRaises(broker_bridge.LiveTradingDisabled):
            broker_bridge.BrokerAdapter("ibkr").submit_order(p)


if __name__=="__main__":
    unittest.main()
