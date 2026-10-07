import copy
import unittest
from unittest.mock import Mock
import paper_simulation as sim

NOW=1791442800000  # 2026-10-08 09:00 Zurich
ISIN='DE000PJ9NCK0'

def market(direction='LONG'):
    long=direction=='LONG'
    return dict(plan=dict(kind='candidate',direction=direction,entry=100.,stop=90. if long else 110.,target=120. if long else 80.,unit='USD/oz'),
                price=100.,priceFresh=True,ready=True,dataAt=NOW,analysisBarAt=NOW,ruleVersion='intraday-responsive-v6',
                direction=direction,mtf=direction,score=80 if long else 20,macd=2 if long else -2,signal=1 if long else -1,atr=10.)

def quote(now=NOW,bid=10.,ask=10.1):
    return dict(isin=ISIN,found=True,marketOpen=True,bid=bid,ask=ask,currency='EUR',source='issuer test',bidAt=now,askAt=now)

def case(direction='LONG'):
    return sim.new_case(market(direction),dict(isin=ISIN,scope='XAU/USD'),quote(),NOW)

def tick(price,seconds=30,direction='LONG',**values):
    return {**market(direction),'price':price,'dataAt':NOW+seconds*1000,**values}

class SimulationTests(unittest.TestCase):
    def test_long_stop_before_any_trail(self):
        c=case();done=sim.advance_case(c,tick(88,suggestedStop=105),quote(NOW+30000,9,9.1),NOW+30000)
        self.assertEqual(done['exitReason'],'stop');self.assertAlmostEqual(done['goldR'],-1.2)
        self.assertEqual(c['status'],'open');self.assertEqual(done['engine']['trade']['stop'],90)

    def test_short_stop_and_target(self):
        stopped=sim.advance_case(case('SHORT'),tick(111,direction='SHORT'),None,NOW+30000)
        target=sim.advance_case(case('SHORT'),tick(79,direction='SHORT'),None,NOW+30000)
        self.assertEqual(stopped['exitReason'],'stop');self.assertEqual(target['exitReason'],'target-exit')
        self.assertAlmostEqual(target['goldR'],2.1)

    def test_never_loosen_stop(self):
        c=sim.advance_case(case(),tick(110,suggestedStop=106),None,NOW+30000)
        self.assertEqual(c['engine']['trade']['stop'],106)
        c=sim.advance_case(c,tick(112,60,suggestedStop=92),None,NOW+60000)
        self.assertGreaterEqual(c['engine']['trade']['stop'],106)

    def test_partial_gain_then_extended_target_and_stop(self):
        c=sim.advance_case(case(),tick(120,suggestedStop=110,suggestedTarget=140,analysisBarAt=NOW+300000),quote(NOW+30000,12,12.1),NOW+30000)
        self.assertEqual(c['status'],'open');self.assertEqual(c['remaining'],.5);self.assertEqual(c['engine']['trade']['target'],140)
        self.assertEqual(c['goldR'],1.)
        c=sim.advance_case(c,tick(109,60),quote(NOW+60000,11,11.1),NOW+60000)
        self.assertEqual(c['exitReason'],'stop');self.assertAlmostEqual(c['goldR'],1.45)
        self.assertAlmostEqual(c['productGrossPct'],((12/10.1-1)+(11/10.1-1))*50)
        self.assertFalse(c['netReturnKnown'])

    def test_gap_never_claims_target_or_profit(self):
        c=sim.advance_case(case(),tick(125,120),quote(NOW+120000,12,12.1),NOW+120000)
        self.assertEqual(c['status'],'inconclusive');self.assertIsNone(c['productGrossPct'])
        self.assertEqual(c['goldR'],0)

    def test_missing_gold_closes_unknown(self):
        c=sim.advance_case(case(),dict(priceFresh=False),None,NOW+91000)
        self.assertEqual(c['status'],'inconclusive')

    def test_old_future_duplicate_clock_does_not_advance(self):
        for at in (NOW,NOW-30000):
            c=sim.advance_case(case(),{**tick(120),'dataAt':at},None,NOW+30000)
            self.assertEqual(c['remaining'],1.)
        self.assertIsNone(sim.fresh_quote(quote(NOW+30000),NOW,ISIN))

    def test_unknown_stale_chart_prices_stay_unknown(self):
        for q in (None,quote(NOW-91000),{**quote(),'priceKind':'issuer-chart'},{**quote(),'currency':'CHF'}):
            c=sim.new_case(market(),dict(isin=ISIN),q,NOW)
            self.assertFalse(c['productReturnKnown'])
        c=sim.advance_case(case(),tick(120),None,NOW+30000)
        self.assertIsNone(c['productGrossPct']);self.assertEqual(c['status'],'closed')

    def test_reversal_closes_before_trailing(self):
        c=sim.advance_case(case(),tick(106,direction='SHORT',suggestedStop=107),None,NOW+30000)
        self.assertEqual(c['exitReason'],'reversal-exit');self.assertEqual(c['engine']['trade']['stop'],90)

    def test_demo_is_closed_labeled_and_not_product_profit(self):
        c=sim.technical_demo(4100,dict(isin=ISIN,name='Gold Long'))
        self.assertTrue(c['demonstration']);self.assertEqual(c['status'],'closed')
        kinds=[e['kind'] for e in c['events']]
        self.assertIn('partial-profit',kinds);self.assertIn('stop-raised',kinds);self.assertIn('target-extended',kinds)
        self.assertIsNone(c['productGrossPct'])

    def test_read_report_does_not_advance_or_write(self):
        conn=Mock();conn.execute.return_value.fetchone.side_effect=[dict_payload:=({'startAt':sim.START},),None,None]
        conn.execute.return_value.fetchall.side_effect=[[],[]]
        r=sim.report(conn,'2026-10-08');self.assertEqual(r['cases'],[])
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in conn.execute.call_args_list))

    def test_scheduled_start_not_backfilled(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=({'startAt':sim.START,'enabled':True},)
        sim.run_once(conn,{},market(),{'choices':[{'isin':ISIN}]},{},sim.START-1)
        sql=[call.args[0] for call in conn.execute.call_args_list]
        self.assertFalse(any('INSERT INTO bob_paper_cases' in q for q in sql))

if __name__=='__main__':unittest.main()
