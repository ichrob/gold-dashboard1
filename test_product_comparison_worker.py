import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
import product_comparison_worker as worker
from test_product_trade_history import PRODUCT,SPOTS,NOW,iso

QUOTE=dict(isin=PRODUCT['isin'],productVerified=True,found=True,fresh=True,
           currency='EUR',bid=21.2,ask=21.3,bidAt=iso(-15),askAt=iso(-15),source='Test issuer')

class ComparisonChecks(unittest.TestCase):
    def test_same_side_identity_and_clocks(self):
        row=worker.comparison(PRODUCT,SPOTS,QUOTE,NOW)
        self.assertEqual(row['side'],'bid')
        self.assertEqual(row['quoted'],QUOTE['bid'])
        self.assertAlmostEqual(row['estimated'],21.11)
        self.assertEqual(row['spotAt'],SPOTS['spot_price_as_of'])
    def test_reject_incompatible_observations(self):
        for change in [dict(isin='DE000PJ9NB98'),dict(currency='CHF'),dict(bidAt=iso(-80)),
                       dict(askAt=iso(1)),dict(priceKind='issuer-chart'),dict(fresh=False),
                       dict(currencyConversion=True),dict(delayed=True),dict(bid=0),
                       dict(sourceFailure=True),dict(productVerified=False)]:
            with self.subTest(change=change):
                self.assertIsNone(worker.comparison(PRODUCT,SPOTS,{**QUOTE,**change},NOW))
    def test_model_changes_are_isolated(self):
        for name in worker.FIELDS:
            changed={**PRODUCT,name:'different'}
            self.assertNotEqual(worker.model_key(PRODUCT),worker.model_key(changed))
    def test_closed_session_never_fetches(self):
        def fail(*args):raise AssertionError('No data access outside session')
        worker.tick(fail,{},fail,NOW+timedelta(days=1))
    def test_list_failure_preserves_trade_capture_and_exit_study(self):
        class Conn:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,args=None):
                self.sql=sql;calls.append((sql,args));return self
            def fetchall(self):return [('test',{'trade':{'product':PRODUCT}})]
            def fetchone(self):return ({'trade':{'product':PRODUCT}},{})
            def commit(self):pass
        calls=[]
        with patch('exit_quality.observe') as exit_observe,patch('product_precision.observe'),patch('metric_quality.product_check'),patch('precision_learning.observe'),patch('metric_quality.pnl_check'),patch('product_list_study.tick',side_effect=RuntimeError('list unavailable')):
            worker.tick(Conn,{'spots':SPOTS},lambda _:QUOTE,NOW)
        exit_observe.assert_called_once()
        self.assertEqual(exit_observe.call_args.args[1],'test')
        self.assertEqual(exit_observe.call_args.args[5],QUOTE['ask'])
        inserts=[args for sql,args in calls if 'INSERT INTO' in sql]
        self.assertEqual(len(inserts),1)
        self.assertEqual(inserts[0][2],worker.history.clock(QUOTE['bidAt']))
        self.assertTrue(any('FOR UPDATE' in sql for sql,_ in calls))
