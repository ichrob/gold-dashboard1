"""Four paper metrics only use confirmed price evidence."""
import unittest
import paper_simulation as sim
import paper_portfolios as portfolios
NOW=1791792000000
ISIN='DE000PJ9NCK0'
def q(bid,ask,at=NOW):
    return dict(isin=ISIN,found=True,marketOpen=True,currency='EUR',
                source='test-issuer',bid=bid,ask=ask,bidAt=at,askAt=at)
class PaperEvidenceTests(unittest.TestCase):
    def test_spread_counted_once_and_observed_drawdown(self):
        m=dict(plan=dict(direction='LONG',entry=4000.,stop=3990.,target=4020.),
               price=4000.,dataAt=NOW,analysisBarAt=NOW,ruleVersion='test')
        c=sim.new_case(m,dict(isin=ISIN),q(9.9,10.),NOW,cash=100.)
        self.assertEqual(c['quantity'],10)
        self.assertAlmostEqual(c['entrySpreadEur'],1.)
        ctl=dict(initialCapital=100.,cash=0.,dayOpeningEquity=100.)
        sim.capital_snapshot(ctl,c,q(9.9,10.),NOW)
        self.assertAlmostEqual(ctl['equity'],99.)
        self.assertAlmostEqual(ctl['maxDrawdownPct'],1.)
    def test_missing_quote_does_not_invent_drawdown(self):
        c=dict(product={'isin':ISIN},remainingUnits=10,pendingUnits=0)
        ctl=dict(initialCapital=100.,cash=0.,dayOpeningEquity=100.)
        sim.capital_snapshot(ctl,c,q(9.,10.),NOW)
        self.assertAlmostEqual(ctl['maxDrawdownPct'],10.)
        sim.capital_snapshot(ctl,c,None,NOW+30000)
        self.assertIsNone(ctl['equity'])
        self.assertIsNone(ctl['currentDrawdownPct'])
        self.assertAlmostEqual(ctl['maxDrawdownPct'],10.)
        self.assertEqual(ctl['quoteMissingChecks'],1)
        sim.capital_snapshot(ctl,c,q(12.,12.1,NOW+60000),NOW+60000)
        self.assertAlmostEqual(ctl['equity'],120.)
        self.assertAlmostEqual(ctl['peakEquity'],120.)
        self.assertEqual(ctl['quoteConfirmedChecks'],2)
    def test_rate_only_from_priced_trades(self):
        r=portfolios.performance_snapshot({'control':{'maxDrawdownPct':8.},
            'daily':[dict(closed=3,inconclusive=1,productKnown=2,productPositive=1),
                     dict(closed=2,inconclusive=0,productKnown=1,productPositive=1)]})
        self.assertEqual(r['pricedTrades'],3)
        self.assertEqual(r['inconclusiveTrades'],1)
        self.assertAlmostEqual(r['productPositiveRatePct'],66.67)
        self.assertFalse(r['netReturnKnown'])
        self.assertIsNone(portfolios.performance_snapshot({'daily':[]})['productPositiveRatePct'])
if __name__=='__main__':
    unittest.main()

class EvidenceSeparationTests(unittest.TestCase):
    def test_model_and_inconclusive_never_count_as_observed_results(self):
        import paper_costs
        base=dict(id='example',status='closed',productReturnKnown=True,remainingUnits=0,pendingUnits=0,
                  plan={'direction':'LONG'},entryAsk=10,productGrossPct=5,events=[])
        observed=dict(base,entryQuote={'ask':10,'askAt':NOW,'source':'example'})
        model=dict(base,priceBasis={'kind':'calculated','price':10})
        missing=dict(base,status='inconclusive')
        out=paper_costs.evidence_report([observed,model,missing])
        self.assertEqual([g['eligible'] for g in out['groups']],[1,0,0])
        self.assertEqual([g['cases'] for g in out['groups']],[1,1,1])
        self.assertIsNone(out['cases'][1]['grossPct'])
        self.assertIsNone(out['cases'][2]['observedMaxDrawdownPct'])
        self.assertFalse(out['actualNetKnown'])

    def test_case_drawdown_uses_observed_bid_and_survives_missing_quote(self):
        m=dict(plan=dict(direction='LONG',entry=4000.,stop=3990.,target=4020.),
               price=4000.,dataAt=NOW,analysisBarAt=NOW,ruleVersion='test',priceFresh=True)
        c=sim.new_case(m,dict(isin=ISIN,priceBasis={'kind':'calculated','price':10}),q(9.9,10.),NOW)
        self.assertEqual(c['priceBasis']['kind'],'calculated')
        down=sim.advance_case(c,m,q(8,8.1,NOW+1000),NOW+1000)
        self.assertAlmostEqual(down['observedMaxDrawdownPct'],20.)
        gap=sim.advance_case(down,m,None,NOW+2000)
        self.assertEqual(gap['observedMaxDrawdownPct'],down['observedMaxDrawdownPct'])
        self.assertEqual(gap['observedValuationChecks'],down['observedValuationChecks'])
