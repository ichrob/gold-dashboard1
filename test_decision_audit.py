import os
import unittest
from datetime import datetime, timezone
import decision_audit as a

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.now=1800000000000
        self.payload=dict(direction='LONG',shadowDirection='NEUTRAL',barAt=self.now-300000,price=100,priceAt=self.now,products=[],selection=[],origin='background')
    def record(self):return a.normalize(self.payload,self.now)[1]
    def test_idempotent_frozen_decision(self):
        key,r=a.normalize(self.payload,self.now)
        self.assertEqual(key,a.normalize(self.payload,self.now+1000)[0])
        self.assertNotEqual(key,a.normalize({**self.payload,'direction':'SHORT'},self.now)[0])
        self.assertTrue(r['marketEvaluable'])
    def test_invalid_or_stale_not_evaluated(self):
        for at in (None,self.now+1,self.now-180001):
            r=a.normalize({**self.payload,'priceAt':at},self.now)[1]
            self.assertIsNone(a.outcome(r,{'at':self.now+900000,'price':101},15))
        with self.assertRaises(ValueError):a.normalize({**self.payload,'barAt':self.now+1},self.now)
    def test_forward_only_outcome_and_neutral(self):
        r=self.record()
        for at in (self.now+899999,self.now+960001):self.assertIsNone(a.outcome(r,{'at':at,'price':101},15))
        self.assertAlmostEqual(a.outcome(r,{'at':self.now+900000,'price':101},15)['directionalPct'],1)
        r['direction']='NEUTRAL';self.assertIsNone(a.outcome(r,{'at':self.now+900000,'price':101},15)['directionalPct'])
    def test_duplicates_and_no_premature_learning(self):
        r=self.record();truths=[{'at':self.now+h*60000,'price':101} for h in (15,60,240)]
        report=a.summarize([(r,truths),(r,truths)])
        self.assertEqual(report['metrics']['60']['evaluated'],1)
        self.assertFalse(report['learning']['ready']);self.assertFalse(report['learning']['automaticRuleChange'])
    def test_product_requires_real_fresh_bid(self):
        r=self.record();r['products']=[dict(isin='DE000FG5NMF2',selected=True,ask=10,quoteAt=self.now)]
        later={**r,'recordedAt':self.now+3600000,'products':[dict(isin='DE000FG5NMF2',bid=11,quoteAt=self.now+3600000)]}
        self.assertEqual(a.product_review([r,later])['evaluated'],1)
        later['products'][0]['quoteAt']=self.now
        self.assertEqual(a.product_review([r,later])['evaluated'],0)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'Postgres fixture unavailable')
class AuditDatabaseTests(unittest.TestCase):
    def test_durable_idempotency_and_report(self):
        import psycopg
        import bob_market_store
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            a.init(conn);bob_market_store.init(conn)
            now=datetime.now(timezone.utc).timestamp()*1000
            payload=dict(direction='NEUTRAL',barAt=now-300000,priceAt=now,price=4000,products=[])
            first=a.write(conn,payload);a.write(conn,payload)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_audit WHERE id=%s',(first['id'],)).fetchone()[0],1)
            a._harvest_at=0
            self.assertGreaterEqual(a.report(conn)['total'],1)
            conn.rollback()
