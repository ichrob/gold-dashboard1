"""Prove sampled model cash-flow reconciliation, NEVER broker profitability.

Original paper case evidence, fixed provisional costs, no raw output.
"""
import copy
import json
import unittest

import paper_costs
import paper_net_evidence as proof
import paper_profit_summary as overview
import bob_diagnostics

T = 1794360000000


def closed_case():
    quantity, ask, bid = 4, 10., 11.5
    model = dict(version='cash-costs-v1',feeEurPerOrder=1.,
                 slippageBpsPerSide=5.,extraHoldingBpsPerDay=0.)
    entry = dict(isin="private-test-instrument", currency="EUR", ask=ask,
                 askAt=T, bid=9.9, bidAt=T, source="public-issuer-test")
    exit_quote = dict(isin="private-test-instrument", currency="EUR",
                      bid=bid, bidAt=T+30000, ask=11.6, source="public-issuer-test")
    c = dict(status="closed",modelOnly=True,productReturnKnown=True,
             startedAt=T,closedAt=T+30000,settledAt=T+30000,
             product=dict(isin=entry["isin"]),entryQuote=entry,
             entryAsk=ask,quantity=quantity,allocated=quantity*ask,
             remainingUnits=0,pendingUnits=0,cashReleased=quantity*bid,
             analysis=dict(dataAt=T),
             entryChecklist=dict(decision="entry",ruleVersion="v1"),
             selectionEvidence=dict(capturedAt=T,selectedIsin=entry["isin"],
                                    rankedShortlist=[dict(isin=entry["isin"])]),
             events=[dict(kind="entry",recordedAt=T),
                     dict(kind="time-exit",units=quantity,quote=exit_quote,
                          recordedAt=T+30000,at=T+30000)],
             ledgerCostModel=model)
    valuation=paper_costs.evaluate(c,model)
    c["ledgerCostsDebited"]=valuation["feesEur"]+valuation["slippageEur"]
    c["ledgerModelNetEur"]=valuation["modelNetEur"]
    return c


class EvidenceTests(unittest.TestCase):
    def test_exact_synchronized_product_quote_and_costs_reconcile_as_model_only(self):
        original=closed_case()
        before=copy.deepcopy(original)
        s=proof.sample([original])
        self.assertEqual(s["sampled"],1)
        self.assertEqual(s["modelEvidenceEligible"],1)
        self.assertEqual(s["excluded"],0)
        self.assertGreater(s["sampleModelNetEur"],0)
        self.assertFalse(s["brokerNetVerified"])
        self.assertFalse(s["fullHistoryRead"])
        self.assertEqual(original,before)
        self.assertNotIn("private-test-instrument",json.dumps(s))
        self.assertNotIn("public-issuer-test",json.dumps(s))

    def test_missing_original_price_or_clock_denies_validation(self):
        for modifier in (
            lambda c: c["entryQuote"].update(source=None),
            lambda c: c["entryQuote"].update(askAt=T-91000),
            lambda c: c["entryQuote"].update(currency="USD"),
            lambda c: c["events"][1]["quote"].update(bidAt=T-91000),
            lambda c: c["events"][1]["quote"].update(bid=None),
            lambda c: c["events"][1]["quote"].update(isin="other"),
            lambda c: c["selectionEvidence"].update(selectedIsin="wrong"),
            lambda c: c["analysis"].update(dataAt=T-61001),
        ):
            c=closed_case()
            modifier(c)
            s=proof.sample([c])
            self.assertEqual(s["modelEvidenceEligible"],0)
            self.assertEqual(s["excluded"],1)
            self.assertFalse(s["brokerNetVerified"])

    def test_mismatched_costs_sales_pending_and_synthetic_are_excluded(self):
        cases=[]
        for change in (
            lambda c: c.update(ledgerCostsDebited=0.),
            lambda c: c.update(ledgerModelNetEur=9999.),
            lambda c: c.update(cashReleased=9999.),
            lambda c: c.update(pendingUnits=1),
            lambda c: c.update(status="inconclusive"),
            lambda c: c.update(demonstration=True),
        ):
            c=closed_case();change(c);cases.append(c)
        for c in cases:
            s=proof.sample([c])
            self.assertEqual(s["modelEvidenceEligible"],0)
            self.assertIsNone(s["sampleModelNetEur"])
        self.assertEqual(proof.sample(None)["status"],"unavailable")
        self.assertEqual(proof.sample([closed_case()]*6)["status"],"partial")

    def test_forward_holdout_cannot_be_promoted_to_broker_net(self):
        forward=dict(version="prospective-paper-v1",startedAt=T,
                     validationAt=T+86400000,excluded=0,
                     calibration=dict(cases=40,netEur=120,grossEur=160),
                     validation=dict(cases=45,netEur=150,grossEur=190),
                     actualNetKnown=True,strategyWinnerConfirmed=True,
                     sensitiveSecret="DO-NOT-EXPOSE")
        safe=overview.safe_forward_evidence(forward)
        self.assertTrue(safe["sufficientModelHoldoutCases"])
        self.assertFalse(safe["actualNetVerified"])
        self.assertFalse(safe["winnerConfirmed"])
        self.assertNotIn("DO-NOT-EXPOSE",str(safe))
        twice=overview.safe_forward_projected(safe)
        self.assertTrue(twice["sufficientModelHoldoutCases"])
        self.assertEqual(twice["validation"]["modelNetEur"],150.)
        self.assertFalse(twice["actualNetVerified"])

    def test_compact_profit_dashboard_reports_model_sample_separately(self):
        a=dict(profile="trend800nov",initialCapital=800.,equity=805.,
               status="running",netEvidenceSample=proof.sample([closed_case()]),
               forwardEvidence=overview.safe_forward_evidence(dict(
                   version="prospective-paper-v1",startedAt=T,
                   validationAt=T+86400000,excluded=0,
                   calibration=dict(cases=40,netEur=100,grossEur=120),
                   validation=dict(cases=45,netEur=50,grossEur=80))),
               privateToken="DO-NOT-EXPOSE",isin="PRIVATE")
        report=overview.snapshot([a])
        self.assertTrue(report["modelNetAuditAvailable"])
        self.assertFalse(report["netProductReturnsVerified"])
        self.assertFalse(report["strategyWinnerConfirmed"])
        self.assertFalse(report["comparableStrategyHoldoutVerified"])
        row=next(x for x in report["rows"] if x.get("profile")=="trend800nov")
        self.assertEqual(row["recentModelNetSample"]["modelEvidenceEligible"],1)
        self.assertTrue(row["forwardEvidence"]["sufficientModelHoldoutCases"])
        self.assertNotIn("PRIVATE",json.dumps(report))
        self.assertNotIn("DO-NOT-EXPOSE",json.dumps(report))
        self.assertIn("brokerExecutionVerified",report)
        focused=bob_diagnostics.focused_report(
            bob_diagnostics.collect({"simulationAndPush":lambda:dict(
                status="observed",accounts=[a])}),"simulation")
        self.assertIn("paperProfitEvidence",focused["areas"])

    def test_unknown_forward_history_never_claims_recovery(self):
        empty=overview.safe_forward_evidence(None)
        self.assertEqual(empty["status"],"not-observed")
        self.assertFalse(empty["winnerConfirmed"])
        bad=overview.safe_forward_evidence(dict(
            version="prospective-paper-v1",startedAt=T,validationAt=T+86400000,
            excluded=0,calibration=dict(cases=100,netEur="secret",grossEur=1000),
            validation=dict(cases=100,netEur=100,grossEur=100)))
        self.assertFalse(bad["sufficientModelHoldoutCases"])
        self.assertFalse(bad["actualNetVerified"])


if __name__=="__main__":
    unittest.main()
