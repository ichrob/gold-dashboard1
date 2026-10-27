import json
import os
import unittest
from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import Mock, patch
import comparison_health as h
import bob_diagnostics


class HealthTests(unittest.TestCase):
    def test_terminal_and_recorded_outcomes_never_become_finished_studies(self):
        r=h.summarize([(Decimal('1000'), 'terminal-not-necessarily-comparable'),
                       (2000, 'outcome-recorded'), (float('nan'),'private-secret')],3000)
        self.assertFalse(r['studyCompletedVerified'])
        self.assertFalse(r['continuousExecutionVerified'])
        self.assertEqual(r['latestSampleAt'],2000)
        self.assertNotIn('private-secret',json.dumps(r))
        self.assertEqual(h.summarize([],3000)['status'],'no-records')

    def test_bounded_sample_rejects_future_clock(self):
        r=h.summarize([(4000,'pending')]*101,3000)
        self.assertTrue(r['truncated'])
        self.assertEqual(r['sampledRecords'],100)
        self.assertIsNone(r['latestSampleAt'])

    def test_one_failed_probe_does_not_hide_other_studies(self):
        conn=Mock();conn.transaction.side_effect=lambda:nullcontext()
        def execute(sql,params):
            self.assertTrue(sql.lstrip().startswith('SELECT'))
            if 'bob_decision_audit' in sql:raise RuntimeError('private database detail')
            cursor=Mock();cursor.fetchall.return_value=[];return cursor
        conn.execute.side_effect=execute
        r=h.report(conn,1793080800000)
        self.assertEqual(r['items']['signals']['status'],'unavailable')
        self.assertEqual(r['items']['list-price-pairs']['status'],'no-records')
        self.assertTrue(r['items']['legacy-fast-cautious']['collectionWindowEnded'])
        self.assertFalse(r['items']['legacy-fast-cautious']['newCasesExpected'])
        self.assertNotIn('private database detail',json.dumps(r))
        self.assertGreater(conn.execute.call_count,10)

    def test_compact_evidence_survives_large_optional_history(self):
        data={'status':'observed','items':{'signals':{'sampledRecords':3}}}
        report=bob_diagnostics.collect({'simulationAndPush':lambda:{
            'status':'observed','comparisonHealth':data,'history':{'padding':'x'*5000}}})
        reduced=bob_diagnostics.bounded_report(report,max_bytes=2200)
        self.assertEqual(reduced['areas']['comparisonHealth'],data)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_readonly_queries_and_savepoint_recovery(self):
        import uuid
        import psycopg
        from psycopg import sql
        schema='comparison_health_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('CREATE TABLE bob_decision_audit (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)')
                conn.execute('CREATE TABLE bob_decision_outcomes (decision_id TEXT, horizon INT, truth JSONB)')
                conn.execute("INSERT INTO bob_decision_audit VALUES ('secret-id',now(),'{\"marketEvaluable\":true}')")
                conn.execute("INSERT INTO bob_decision_outcomes VALUES ('secret-id',60,'{}')")
                conn.execute('CREATE TABLE bob_ranking_samples (currency TEXT,slot BIGINT,outcome JSONB)')
                conn.execute("INSERT INTO bob_ranking_samples VALUES ('EUR',1000,'{\"complete\":false}'),('CHF',1000,'{\"complete\":true}')")
                conn.execute('CREATE TABLE bob_precision_learning (id TEXT,state JSONB)')
                conn.execute("INSERT INTO bob_precision_learning VALUES ('private-identity','{\"phase\":\"validation\",\"lastAt\":1000}')")
                conn.commit()
                conn.execute('SET TRANSACTION READ ONLY')
                r=h.report(conn)
                self.assertEqual(r['items']['signals']['counts'],{'eligible':1})
                self.assertEqual(r['items']['signal-outcomes']['counts'],{'outcome-recorded':1})
                self.assertEqual(r['items']['ranking-EUR']['counts'],{'incomplete':1})
                self.assertEqual(r['items']['ranking-CHF']['counts'],{'comparable':1})
                self.assertEqual(r['items']['price-correction-states']['counts'],{'validation':1})
                self.assertNotIn('secret-id',json.dumps(r))
                self.assertNotIn('private-identity',json.dumps(r))
                conn.commit()
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
