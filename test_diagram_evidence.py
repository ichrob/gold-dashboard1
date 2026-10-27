"""Prospective chart evidence must not change production exits or reuse fitted prices."""
import copy
import json
import unittest
import precision_learning as precision
import ranking_lifecycle as life
import test_ranking_extensions as fixtures
from test_paper_ko_guard import NOW,ISIN,quote

class DiagramEvidenceTests(unittest.TestCase):
    def test_fixed_shadow_remains_open_after_bob_reversal_and_keeps_quote_gates(self):
        state,m,q=fixtures.ExitTests().state()
        state['fixedCases']=copy.deepcopy(state['cases'])
        state['fixedCases'][ISIN]['comparisonFixedPlan']=True
        at=NOW+30000
        out=life.advance_state(state,{**m,'direction':'SHORT','price':4010.,'dataAt':at},
            {ISIN:quote(at,ko=3500.)},at)
        self.assertEqual(out['cases'][ISIN]['status'],'closed')
        self.assertEqual(out['fixedCases'][ISIN]['status'],'open')
        self.assertEqual(out['fixedCases'][ISIN]['engine']['trade']['stop'],m['plan']['stop'])
        self.assertEqual(out['fixedCases'][ISIN]['remaining'],1)
        later=life.advance_state(out,{**m,'dataAt':at+30000},{},at+30000)
        self.assertEqual(later['fixedCases'][ISIN]['status'],'inconclusive')
        self.assertFalse(later['fixedCases'][ISIN]['productReturnKnown'])
        self.assertEqual(state['cases'][ISIN]['status'],'open')

    def test_fixed_plan_keeps_original_target_without_partial_sale(self):
        state,m,q=fixtures.ExitTests().state()
        state['fixedCases']=copy.deepcopy(state['cases'])
        state['fixedCases'][ISIN]['comparisonFixedPlan']=True
        at=NOW+30000
        out=life.advance_state(state,{**m,'price':4310.,'dataAt':at},
            {ISIN:quote(at,ko=3500.,bid=11.)},at)
        fixed=out['fixedCases'][ISIN]
        self.assertEqual(fixed['status'],'closed')
        self.assertFalse(fixed['partialTaken'])
        self.assertEqual(fixed['exitReason'],'target-exit')
        self.assertTrue(out['cases'][ISIN]['partialTaken'])
        self.assertIn('observedPeakPct',fixed)

    def test_price_chart_freezes_correction_before_observation(self):
        class Conn:
            def __init__(self):self.state=precision.initial()
            def execute(self,sql,args=None):
                if sql.startswith('SELECT paused'):self.result=(False,)
                elif sql.startswith('SELECT state'):self.result=(self.state,)
                elif sql.startswith('UPDATE bob_precision_learning'):self.state=json.loads(args[0])
                return self
            def fetchone(self):return self.result
        conn=Conn();product=dict(isin=ISIN,currency='EUR')
        for i in range(31):
            precision.observe(conn,product,dict(at=NOW+i*60000,quoted=10.1,estimated=10.,source='issuer'))
        history=conn.state['chartHistory']
        self.assertIsNone(history[29]['corrected'],'Training end cannot be its own validation sample')
        self.assertAlmostEqual(history[30]['corrected'],10.1)
        precision.observe(conn,product,dict(at=NOW+34*60000,quoted=10.1,estimated=10.,source='issuer'))
        self.assertIsNone(conn.state['chartHistory'][-1]['corrected'],'Gap revokes the display lease')
        self.assertEqual(conn.state['phase'],'training')

    def test_portfolio_chart_report_is_bounded_and_read_only(self):
        import paper_portfolios as portfolios
        class Conn:
            def __init__(self):self.queries=[]
            def execute(self,sql,args=()):self.queries.append(sql);return self
            def fetchone(self):return ({'initialCapital':100,'secret':'excluded'},)
            def fetchall(self):return [('2026-10-16',{'capital':110,'initialCapital':100,'valuationKnown':True,'extra':'excluded'})]
        conn=Conn();result=portfolios.diagram_report(conn)
        self.assertEqual(len(result['accounts']),7)
        self.assertFalse(result['realOrders'])
        self.assertTrue(all(q.startswith('SELECT') and 'cases' not in q for q in conn.queries))
        self.assertNotIn('secret',json.dumps(result));self.assertNotIn('extra',json.dumps(result))
