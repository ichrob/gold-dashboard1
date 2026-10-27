"""Isolated regressions for authenticated background model curve; no live broker access."""
import copy
import unittest
from datetime import datetime, timezone, timedelta

import product_trade_history as chart

NOW=datetime(2026,10,16,9,40,tzinfo=timezone.utc)
def iso(delta):
    return (NOW+timedelta(seconds=delta)).isoformat()
PRODUCT=dict(isin='DE000FC1CHB7',direction='LONG',currency='EUR',
 simpleSpotTurbo=True,referenceConfirmed=True,bid=20.0,goldReference=4200.0,
 fxReference=.9,ratio=.1,strike=4000.0,ko=4000.0)
SPOTS=dict(xaus=4210.0,is_genuine_xauusd_spot=True,spot_error=None,
 spot_price_as_of=iso(-15),usd_eur_meta=dict(rate=.91,fetchedAt=iso(-20),error=None))

class ProductCurveChecks(unittest.TestCase):
    def test_verified_gold_fx_formula(self):
        result=chart.calculate(PRODUCT,SPOTS,NOW)
        self.assertIsNotNone(result)
        expected=20+.1*((4210-4000)*.91-(4200-4000)*.9)
        self.assertAlmostEqual(result['price'],expected,places=5)
        self.assertEqual(result['kind'],'model')
        self.assertEqual(result['provenance'],'estimated-not-executable')
    def test_native_chf_and_short(self):
        p={**PRODUCT,'currency':'CHF','direction':'SHORT','strike':4480.,'ko':4480.,'fxReference':.8}
        q={**SPOTS,'usd_chf_meta':dict(rate=.82,fetchedAt=iso(-20))}
        actual=chart.calculate(p,q,NOW)
        expected=20-.1*((4210-4480)*.82-(4200-4480)*.8)
        self.assertAlmostEqual(actual['price'],expected,places=5)
        self.assertEqual(actual['currency'],'CHF')
    def test_reject_stale_conflicting_or_invalid(self):
        for p,q in [
            (PRODUCT,{**SPOTS,'spot_price_as_of':iso(-90)}),
            (PRODUCT,{**SPOTS,'usd_eur_meta':dict(rate=.91,fetchedAt=iso(-120))}),
            (PRODUCT,{**SPOTS,'usd_eur_meta':dict(rate=.91,fetchedAt=iso(-76))}),
            (PRODUCT,{**SPOTS,'is_genuine_xauusd_spot':False}),
            (PRODUCT,{**SPOTS,'spot_error':'stale'}),
            (PRODUCT,{**SPOTS,'usd_eur_meta':dict(rate=.91,fetchedAt=iso(20))}),
            (PRODUCT,{**SPOTS,'xaus':3995.}),
            ({**PRODUCT,'referenceConfirmed':False},SPOTS),
            ({**PRODUCT,'isin':'INVALID'},SPOTS),
            ({**PRODUCT,'ratio':0},SPOTS),
            ({**PRODUCT,'currency':'GBP'},SPOTS),
            ({**PRODUCT,'direction':'SHORT','ko':4200.},SPOTS),
        ]:
            with self.subTest(product=p,spot=q):
                self.assertIsNone(chart.calculate(p,q,NOW))
    def test_skip_write_when_no_evidence(self):
        class FakeDB:
            def execute(self,*a):raise AssertionError('Unverified data must not reach database')
        self.assertFalse(chart.append(FakeDB(),'trade-1',PRODUCT,{'xaus':4200},NOW))
    def test_keep_original_clocks_and_retain_model_evidence(self):
        class FakeDB:
            def __init__(self):
                self.calls=[]
            def execute(self,sql,args):
                self.calls.append((sql,args))
        db=FakeDB()
        self.assertTrue(chart.append(db,'trade-1',PRODUCT,SPOTS,NOW))
        self.assertEqual(len(db.calls),1)
        insert_sql,args=db.calls[0]
        self.assertIn('ON CONFLICT DO NOTHING',insert_sql)
        self.assertEqual(args[1],iso(-15))
        self.assertEqual(args[2],iso(-20))
        self.assertEqual(args[4],'EUR')
        self.assertEqual(__import__('json').loads(args[5])['provenance'],'estimated-not-executable')

if __name__=='__main__':unittest.main()
