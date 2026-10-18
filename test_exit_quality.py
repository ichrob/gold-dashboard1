import copy
import json
import os
import unittest
from unittest.mock import patch
import exit_quality as q

class ExitQualityTests(unittest.TestCase):
    def setUp(self):
        self.now=q.START
        self.product=dict(isin='DE000FC1CHB7',currency='EUR',direction='LONG',bid=10,
            goldReference=4000,fxReference=1,ratio=.1,strike=3900,ko=3900)
        self.trade=dict(product=self.product,stop=3990,target=4030)
        self.row=dict(at=self.now,quoted=10,currency='EUR',source='issuer',kind='issuer',side='bid')
        self.point=dict(fxRate=1,fxAt='2026-10-19T06:00:00Z')
    def seed(self):
        return q.seed(self.trade,self.row,self.point,10.1,self.now)
    def full(self,case,prices=None):
        for i in range(1,121):
            bid=prices.get(i,11) if prices else 11
            q.append(case,dict(self.row,at=self.now+i*30000,quoted=bid),case['modelKey'],self.now+i*30000)
        return q.evaluate(case,self.now+3600000)
    def test_freeze_original_plan_and_product_prices(self):
        c=self.seed()
        self.assertEqual(c['stop'],9);self.assertEqual(c['target'],13);self.assertEqual(c['entry'],10.1)
        self.assertEqual(c['quoteAt'],self.now)
        self.assertEqual(c['points'],[])
        self.trade['stop']=3980
        self.assertEqual(c['stop'],9)
    def test_native_short_is_bought_certificate_not_inverse_return(self):
        self.product.update(direction='SHORT',strike=4100,ko=4100)
        self.trade.update(stop=4010,target=3970)
        c=self.seed()
        self.assertEqual(c['stop'],9);self.assertEqual(c['target'],13)
        r=self.full(c)
        self.assertGreater(r['scenarios'][0]['baselinePct'],0)
    def test_trailing_uses_previous_peak_not_future_prices(self):
        c=self.seed();r=self.full(c,{1:12,2:10.8})
        self.assertEqual(r['status'],'complete');self.assertEqual(r['coveragePct'],100)
        self.assertEqual(r['referenceExits']['trailing']['at'],self.now+60000)
        self.assertEqual(r['referenceExits']['trailing']['bid'],10.8)
        self.assertEqual(r['referenceExits']['fixed']['reason'],'horizon')
        self.assertLess(r['scenarios'][0]['differencePct'],0)
    def test_gap_and_source_change_prevent_cost_verdict(self):
        for change in ('gap','source'):
            c=self.seed()
            for i in range(1,121):
                if change=='gap' and 20<=i<=30:continue
                row=dict(self.row,at=self.now+i*30000,quoted=11)
                if change=='source' and i==40:row['source']='other'
                q.append(c,row,c['modelKey'],self.now+i*30000)
            r=q.evaluate(c,self.now+3900000)
            self.assertEqual(r['status'],'missing');self.assertEqual(r['scenarios'],[])
    def test_duplicate_stale_and_wrong_currency_not_coverage(self):
        c=self.seed();row=dict(self.row,at=self.now+30000)
        q.append(c,row,c['modelKey'],self.now+30000);q.append(c,row,c['modelKey'],self.now+30000)
        q.append(c,dict(row,at=self.now+60000),c['modelKey'],self.now+200000)
        q.append(c,dict(row,currency='CHF',at=self.now+90000),c['modelKey'],self.now+90000)
        self.assertEqual(len(c['points']),1)
    def test_rebound_and_target_pullback_are_observations(self):
        r=self.full(self.seed(),{1:8.8,2:12})
        self.assertTrue(r['stopRecoveredEntry']);self.assertGreater(r['stopReboundPct'],0)
        self.assertEqual(r['referenceExits']['fixed']['bid'],8.8) # never assume stop-level fill
        r=self.full(self.seed(),{1:13.2,2:10})
        self.assertGreater(r['targetPullbackPct'],0)
    def test_missing_target_or_prior_start_does_not_create_case(self):
        self.assertIsNone(q.seed(dict(self.trade,target=None),self.row,self.point,10.1,self.now))
        self.assertIsNone(q.seed(self.trade,self.row,self.point,10.1,self.now-1))
        self.assertIsNone(q.seed(self.trade,dict(self.row,currency='CHF'),self.point,10.1,self.now))


@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class ExitQualityDatabaseTests(ExitQualityTests):
    def test_persistent_case_dedup_and_frozen_protocol(self):
        import psycopg,uuid
        schema='exit_quality_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            try:
                q.init(conn)
                q.observe(conn,'test-trade',self.trade,self.row,self.point,10.1,self.now)
                altered=dict(self.trade,stop=3980)
                q.observe(conn,'test-trade',altered,dict(self.row,at=self.now+30000,quoted=12),self.point,12.1,self.now+30000)
                q.observe(conn,'test-trade',altered,dict(self.row,at=self.now+30000,quoted=12),self.point,12.1,self.now+30000)
                raw=conn.execute('SELECT payload FROM bob_exit_quality_cases').fetchone()[0]
                self.assertEqual(raw['stop'],9);self.assertEqual(len(raw['points']),1)
                report=q.read(conn,self.now+3900000)
                self.assertEqual(report['items'][0]['status'],'missing')
                self.assertFalse(report['ordersPlaced'])
                q.init(conn)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_exit_quality_cases').fetchone()[0],1)
                conn.execute('UPDATE bob_exit_quality_protocol SET payload=%s::jsonb',('{}',))
                with self.assertRaises(ValueError):q.read(conn,self.now)
            finally:
                conn.rollback()
                conn.execute('DROP SCHEMA IF EXISTS '+schema+' CASCADE');conn.commit()
