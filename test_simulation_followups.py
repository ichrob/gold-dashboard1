import json
import os
import time
import unittest
import uuid
import model_gap_review as model
import evidence_repair as repair


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI')
class FollowupTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.c=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'])
        self.schema='followups_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+self.schema)
        self.c.execute('SET search_path TO '+self.schema)
        repair.init(self.c)
        self.c.execute('CREATE TABLE bob_decision_audit(id TEXT PRIMARY KEY,recorded_at TIMESTAMPTZ,payload JSONB)')
        self.c.execute('CREATE TABLE bob_decision_outcomes(decision_id TEXT,horizon INT,truth JSONB,PRIMARY KEY(decision_id,horizon))')
        self.c.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
        self.c.execute('CREATE INDEX spot_time ON bob_spot_observations(stream,quote_at)')
        self.c.execute('CREATE TABLE bob_ranking_samples(currency TEXT,slot BIGINT,payload JSONB,outcome JSONB)')
        self.c.execute('CREATE TABLE bob_ranking_lifecycles(currency TEXT,slot BIGINT,result JSONB,complete BOOLEAN)')
        self.c.commit()
        self.now=int(time.time()*1000)

    def tearDown(self):
        self.c.rollback()
        self.c.execute('DROP SCHEMA '+self.schema+' CASCADE')
        self.c.commit();self.c.close()

    def decision(self,key,age,eligible=True):
        at=self.now-age*60000
        row=dict(recordedAt=at,price=4000.,direction='LONG',marketEvaluable=eligible)
        self.c.execute('INSERT INTO bob_decision_audit VALUES(%s,to_timestamp(%s/1000.0),%s::jsonb)',(key,at,json.dumps(row)))
        return at

    def point(self,at,price):
        self.c.execute('INSERT INTO bob_spot_observations VALUES(%s,to_timestamp(%s/1000.0),%s)',(model.STREAM,at,price))

    def test_new_60m_gap_discovered_despite_busy_15m_lane_and_archive_cursor(self):
        for i in range(40):self.decision('recent-'+str(i),17+i/100)
        at=self.decision('mature',62)
        self.c.execute("UPDATE bob_test_repair_control SET signal_cursor='zzz' WHERE id=1")
        repair.discover(self.c,self.now)
        self.assertIsNotNone(self.c.execute("SELECT id FROM bob_test_repairs WHERE id='signal:mature:60'").fetchone())
        # Recovery still prefers an actual original, without a modeled insert.
        self.point(at+3600000,4010.)
        ok,_,_=repair.retry_signal(self.c,dict(decision='mature',horizon=60))
        self.assertTrue(ok)
        self.assertEqual(self.c.execute("SELECT truth->>'price' FROM bob_decision_outcomes WHERE decision_id='mature' AND horizon=60").fetchone()[0],'4010.0')

    def test_readonly_diagnostic_separates_window_harvest_estimate_and_missing(self):
        self.decision('pending',60.5)
        at=self.decision('harvest',63);self.point(at+3600000,4005.)
        self.decision('estimated',66)
        self.c.execute('INSERT INTO bob_gap_models VALUES(%s,%s,%s::jsonb)',
            ('signal:estimated:60',self.now,json.dumps(dict(status='modelled',originalEvidenceComplete=False))))
        self.decision('unavailable',69)
        self.c.execute("INSERT INTO bob_gap_models VALUES('signal:unavailable:60',%s,'{\"status\":\"unavailable\"}')",(self.now,))
        self.decision('not-modeled',72)
        self.decision('invalid',75,False)
        self.c.commit();self.c.execute('SET TRANSACTION READ ONLY')
        out=model.recent_followups(self.c,self.now)
        self.assertEqual([i['state'] for i in out['items']],['source-window-pending',
            'original-awaiting-harvest','estimated','original-missing-model-unavailable',
            'original-missing-model-pending','invalid-original-start'])
        self.assertEqual(sum(i['modelIncluded'] for i in out['items']),1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM bob_decision_outcomes').fetchone()[0],0)
        self.assertTrue(out['originalEvidenceUnchanged'])

    def test_retro_model_uses_bracket_and_is_frozen_without_filling_original_table(self):
        at=self.decision('model',65);target=at+3600000
        self.point(at,4000.);self.point(target-120000,4010.);self.point(target+120000,4014.)
        repair.enqueue(self.c,'signal:model:60','signal',dict(decision='model',horizon=60),dict(at=at),self.now)
        model.tick(self.c,self.now)
        first=self.c.execute("SELECT payload FROM bob_gap_models WHERE id='signal:model:60'").fetchone()[0]
        self.assertEqual(first['status'],'modelled')
        self.assertEqual(first['end']['price'],4012.)
        self.assertTrue(first['retrospectivelyCalculated'])
        self.assertFalse(first['usedForLearning'])
        self.assertEqual(self.c.execute('SELECT count(*) FROM bob_decision_outcomes').fetchone()[0],0)
        # A later original goes into the original table via recovery, without
        # changing the frozen model's inputs or its initial calculatedAt.
        self.point(target,4013.)
        self.assertTrue(repair.retry_signal(self.c,dict(decision='model',horizon=60))[0])
        model.tick(self.c,self.now+3600001)
        later=self.c.execute("SELECT payload FROM bob_gap_models WHERE id='signal:model:60'").fetchone()[0]
        self.assertEqual(later['end'],first['end'])
        self.assertEqual(later['calculatedAt'],first['calculatedAt'])


if __name__=='__main__':unittest.main()
