import copy
import unittest
from unittest.mock import patch
import product_precision as p
from test_product_comparison_worker import QUOTE
from test_product_trade_history import NOW,SPOTS,PRODUCT


class PrecisionTests(unittest.TestCase):
    def case(self):
        start=1800000000000
        return dict(at=start,quote=dict(isin='one',currency='EUR',source='native',bid=10,ask=10.1),
            model=dict(goldReference=4200,fxReference=.9,ratio=.1,direction='LONG'),
            plan=dict(kind='candidate',unit='USD/oz',entry=4200,stop=4190,target=4220,direction='LONG'),
            predictedStop=9.1,predictedTarget=11.8)
    def points(self,case):
        return [dict(isin='one',currency='EUR',source='native',at=case['at']+i*30000,
            bid=10,ask=10.1,gold=4200,goldAt=case['at']+i*30000,fx=.9) for i in range(1,481)]
    def test_native_identity_time_side_and_currency_validation(self):
        now=NOW.timestamp()*1000
        self.assertIsNotNone(p.native(QUOTE,now))
        for changes in (dict(priceKind='issuer-chart'),dict(currencyConversion=True),dict(delayed=True),
                        dict(bid=1000),dict(fresh=False),dict(currency='USD'),dict(bidAt='bad')):
            self.assertIsNone(p.native(dict(QUOTE,**changes),now))
    def test_frozen_return_includes_spread_and_cost_scenarios(self):
        c=self.case();original=copy.deepcopy(c);points=self.points(c)
        r=p.evaluate(c,points,c['at']+4*p.HOUR)
        self.assertAlmostEqual(r['quoteReturnPct'],(10/10.1-1)*100)
        self.assertAlmostEqual(r['stressScenarioPct'],r['quoteReturnPct']-.3)
        self.assertFalse(r['netProfitKnown']);self.assertEqual(c,original)
        self.assertNotIn('realizedElasticity',r)
    def test_missing_foreign_or_late_truth_never_becomes_win(self):
        c=self.case();points=self.points(c)
        for change in (dict(currency='CHF'),dict(source='other'),dict(isin='two')):
            r=p.evaluate(c,[dict(x,**change) for x in points],c['at']+4*p.HOUR)
            self.assertIsNone(r['quoteReturnPct']);self.assertTrue(r['returnMissing'])
        r=p.evaluate(c,[x for x in points if not c['at']+p.HOUR<=x['at']<=c['at']+p.HOUR+60000],c['at']+4*p.HOUR)
        self.assertIsNone(r['quoteReturnPct'])
    def test_stop_target_match_and_gap_inconclusive(self):
        c=self.case();points=self.points(c)
        points[9].update(gold=4221,bid=12)
        r=p.evaluate(c,points,c['at']+4*p.HOUR)
        self.assertEqual(r['levelError']['kind'],'target')
        self.assertAlmostEqual(r['levelError']['error'],-.2)
        r=p.evaluate(c,points[9:],c['at']+4*p.HOUR)
        self.assertEqual(r['goldPlan']['status'],'inconclusive');self.assertNotIn('levelError',r)
    def test_conflicting_source_time_is_not_selected_favorably(self):
        c=self.case();points=self.points(c)
        points.append(dict(points[0],bid=20))
        self.assertEqual(p.evaluate(c,points,c['at']+4*p.HOUR)['status'],'conflict')
    def test_freeze_uses_only_verified_original_model(self):
        now=NOW.timestamp()*1000
        market=dict(ready=True,priceFresh=True,plan=dict(kind='candidate',unit='USD/oz',
            entry=4200,stop=4190,target=4220,direction='LONG'))
        model=dict(product=PRODUCT,source=QUOTE['source'])
        with patch('product_list_study.anchor',return_value=model):
            row=p.freeze(market,dict(direction='LONG'),QUOTE,SPOTS,now)
            self.assertIsNotNone(row)
            self.assertIsNone(p.freeze(market,dict(direction='LONG',estimated=True),QUOTE,SPOTS,now))
