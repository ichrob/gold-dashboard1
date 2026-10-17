import json
import os
import unittest
from contextlib import nullcontext
from unittest.mock import patch
import evidence_repair as repair

class RepairTests(unittest.TestCase):
    def test_retries_are_bounded_and_only_verified_success_closes(self):
        class Conn:
            def __init__(self):self.attempts=0;self.status='trying';self.payload={'history':[]};self.next=0
            def transaction(self):return nullcontext()
            def execute(self,sql,args=()):
                if sql.startswith('UPDATE bob_test_repairs'):
                    self.status,self.attempts,self.next,raw,_=args;self.payload=json.loads(raw)
                return self
            def fetchall(self):return [('x','signal',{},self.attempts,self.payload)] if self.status=='trying' else []
        conn=Conn()
        with patch.object(repair,'reconcile'),patch.object(repair,'discover'),patch.object(repair,'retry_signal',return_value=(False,False,'Originalkurs fehlt')):
            for i in range(3):repair.tick(conn,1000+i*repair.INTERVAL)
        self.assertEqual(conn.status,'escalated');self.assertEqual(conn.attempts,3)
        self.assertEqual(len(conn.payload['history']),3)
        conn=Conn()
        with patch.object(repair,'reconcile'),patch.object(repair,'discover'),patch.object(repair,'retry_signal',return_value=(True,False,'Original bestätigt')):
            repair.tick(conn,1000)
        self.assertEqual(conn.status,'recovered')

    def test_archive_failure_is_not_recovery(self):
        from unittest.mock import MagicMock
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[('x','signal',{},0,{'history':[]})]
        with patch.object(repair,'reconcile'),patch.object(repair,'discover'),patch.object(repair,'retry_signal',side_effect=RuntimeError('sensitive')):
            repair.tick(conn,1000)
        updates=[c.args[1] for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE bob_test_repairs')]
        self.assertEqual(updates[0][0],'trying');self.assertNotIn('sensitive',updates[0][3])

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class RepairPersistenceTests(unittest.TestCase):
    def test_recovery_exact_time_persistence_and_no_frozen_rewrite(self):
        import psycopg,uuid,time
        from psycopg import sql
        schema='repair_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                repair.init(conn)
                conn.execute('CREATE TABLE bob_ranking_samples(currency TEXT,slot BIGINT,payload JSONB,outcome JSONB)')
                conn.execute('CREATE TABLE bob_ranking_lifecycles(currency TEXT,slot BIGINT,result JSONB,state JSONB,complete BOOLEAN)')
                conn.execute('CREATE TABLE bob_precision_quotes(isin TEXT,source TEXT,currency TEXT,at BIGINT,payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_audit(id TEXT PRIMARY KEY,recorded_at TIMESTAMPTZ,payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_outcomes(decision_id TEXT,horizon INTEGER,truth JSONB,PRIMARY KEY(decision_id,horizon))')
                conn.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
                now=int(time.time()*1000);start=now-30*60000
                payload=dict(recordedAt=start,marketEvaluable=True,price=4000.,direction='LONG')
                conn.execute("INSERT INTO bob_decision_audit VALUES('signal',to_timestamp(%s/1000.0),%s::jsonb)",(start,json.dumps(payload)))
                frozen=dict(at=start,marketReady=True,candidates=[],missing=['DETEST'])
                outcome=dict(complete=False,status='incomplete',missing=['DETEST'])
                conn.execute("INSERT INTO bob_ranking_samples VALUES('EUR',%s,%s::jsonb,%s::jsonb)",(start,json.dumps(frozen),json.dumps(outcome)))
                repair.tick(conn,now);conn.commit()
                states=dict(conn.execute('SELECT kind,status FROM bob_test_repairs').fetchall())
                self.assertEqual(states,{'title':'escalated','signal':'trying'})
                # A present-day price is NOT accepted for a missing historical outcome.
                conn.execute("INSERT INTO bob_spot_observations VALUES('gold-api-xau-usd-v1',to_timestamp(%s/1000.0),4100)",(now,))
                repair.tick(conn,now+repair.INTERVAL)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_decision_outcomes').fetchone()[0],0)
                target=start+15*60000
                conn.execute("INSERT INTO bob_spot_observations VALUES('gold-api-xau-usd-v1',to_timestamp(%s/1000.0),4010)",(target,))
                repair.tick(conn,now+2*repair.INTERVAL);conn.commit();repair.init(conn)
                report=repair.report(conn)
                self.assertEqual(report['counts']['recovered'],1);self.assertEqual(report['counts']['escalated'],1)
                self.assertEqual(report['items'][0]['attempts'],1)
                truth=conn.execute('SELECT truth FROM bob_decision_outcomes').fetchone()[0]
                self.assertEqual(truth['at'],target);self.assertEqual(truth['price'],4010)
                self.assertEqual(conn.execute('SELECT outcome FROM bob_ranking_samples').fetchone()[0],outcome)
                self.assertEqual(report['workerCheckedAt'],now+2*repair.INTERVAL)
                # A separately recovered/backfilled signal must leave the help queue.
                conn.execute("UPDATE bob_test_repairs SET status='escalated' WHERE kind='signal'")
                repair.tick(conn,now+3*repair.INTERVAL)
                self.assertEqual(repair.report(conn)['counts']['recovered'],1)
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
