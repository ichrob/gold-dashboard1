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

    def test_fresh_signal_outcome_waits_for_60_minute_horizon(self):
        query = h.QUERIES['signal-outcomes']
        self.assertIn("a.recorded_at > now() - interval '60 minutes'", query)
        self.assertLess(query.index("'outcome-recorded'"), query.index("'pending-horizon'"))
        self.assertLess(query.index("'pending-horizon'"), query.index("'outcome-not-recorded'"))
        counts = h.summarize([(1000, 'pending-horizon'), (1000, 'outcome-not-recorded'),
                              (1000, 'outcome-recorded')], 2000)['counts']
        self.assertEqual(counts, {'pending-horizon': 1, 'outcome-not-recorded': 1,
                                  'outcome-recorded': 1})

    def test_ineligible_improvement_trial_is_not_a_missing_outcome(self):
        query = h.QUERIES['improvement-trials']
        self.assertIn("'trial-not-evaluable'", query)
        self.assertIn("payload->>'ready' IS DISTINCT FROM 'true'", query)
        self.assertIn("jsonb_typeof(payload->'adx') IS DISTINCT FROM 'number'", query)
        self.assertIn("jsonb_typeof(payload->'at') IS DISTINCT FROM 'number'", query)
        self.assertIn("interval '60 minutes'", query)
        self.assertLess(query.index("'outcome-recorded'"), query.index("'trial-not-evaluable'"))
        self.assertLess(query.index("'trial-not-evaluable'"), query.index("'pending-horizon'"))
        self.assertLess(query.index("'pending-horizon'"), query.index("'outcome-not-recorded'"))
        counts = h.summarize([(1000, 'trial-not-evaluable'), (1000, 'pending-horizon'),
                              (1000, 'outcome-not-recorded')], 2000)['counts']
        self.assertEqual(counts, {'trial-not-evaluable': 1, 'pending-horizon': 1,
                                  'outcome-not-recorded': 1})

    def test_list_price_pair_probe_uses_bounded_current_list_index_lookups(self):
        query = h.QUERIES['list-price-pairs']
        self.assertIn('FROM bob_list_price_anchors ORDER BY isin LIMIT 12', query)
        self.assertIn('CROSS JOIN LATERAL', query)
        self.assertIn('WHERE isin=anchors.isin ORDER BY quote_at DESC LIMIT 101', query)
        self.assertIn('ORDER BY p.quote_at DESC LIMIT 101', query)
        self.assertNotIn('FROM bob_list_price_pairs ORDER BY quote_at DESC', query)

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
        self.assertEqual(r['items']['list-price-pairs']['sampleScope'],'current-list-anchors-only')
        self.assertFalse(r['items']['list-price-pairs']['historicalCoverageVerified'])
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
    def test_list_price_pairs_bounded_current_anchor_sample(self):
        import psycopg
        import uuid
        import time
        from psycopg import sql
        schema = 'pair_health_' + uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('CREATE TABLE bob_list_price_anchors (isin TEXT PRIMARY KEY, payload JSONB NOT NULL)')
                conn.execute('''CREATE TABLE bob_list_price_pairs (
                    identity TEXT NOT NULL, isin TEXT NOT NULL,
                    quote_at TIMESTAMPTZ NOT NULL, evidence JSONB NOT NULL,
                    PRIMARY KEY(identity,quote_at))''')
                conn.execute('CREATE INDEX bob_list_price_time ON bob_list_price_pairs(isin,quote_at DESC)')
                conn.execute("INSERT INTO bob_list_price_anchors VALUES ('DE000FG14AV8','{}'::jsonb)")
                conn.execute("""INSERT INTO bob_list_price_pairs
                    SELECT 'active-'||n, 'DE000FG14AV8',
                           now()-interval '1 day'+n*interval '1 second', '{}'::jsonb
                    FROM generate_series(1,120) AS n""")
                # Recent unanchored history must not be silently reclassified
                # as current-list data; it remains in the underlying table.
                conn.execute("""INSERT INTO bob_list_price_pairs
                    SELECT 'historical-'||n, 'DE000FG4JXV7',
                           now()-interval '1 hour'+n*interval '1 second', '{}'::jsonb
                    FROM generate_series(1,120) AS n""")
                conn.commit()
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    rows = conn.execute(h.QUERIES['list-price-pairs']).fetchall()
                    archived = conn.execute("SELECT count(*) FROM bob_list_price_pairs WHERE isin='DE000FG4JXV7'").fetchone()[0]
                self.assertEqual(len(rows), 101)
                self.assertEqual(archived, 120)
                self.assertTrue(all(label == 'paired-observation' for _,label in rows))
                self.assertLess(max(float(at) for at,_ in rows),
                                (time.time()-23*3600)*1000)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()

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
                conn.execute('CREATE TABLE bob_ranking_samples (currency TEXT,slot BIGINT,outcome JSONB,payload JSONB)')
                conn.execute("INSERT INTO bob_ranking_samples VALUES ('EUR',1000,'{\"complete\":false}','{}'),('CHF',1000,'{\"complete\":true}','{}')")
                conn.execute('CREATE TABLE bob_improvement_trials (campaign TEXT,slot BIGINT,payload JSONB,outcome JSONB)')
                import improvement_tracker
                campaign = improvement_tracker.VERSION
                # Preserve outcome evidence; ineligible neutral cases cannot have
                # a directional trade result, and recent eligible cases aren't due.
                cases = (
                    (1, '{"valid":true,"ready":true,"adx":30,"at":1000}', '{"complete":true}'),
                    (2, '{"valid":true,"ready":false,"adx":30,"at":1000}', None),
                    (3, '{"valid":true,"ready":true,"adx":30,"at":1000}', None),
                )
                for slot,payload,outcome in cases:
                    conn.execute('INSERT INTO bob_improvement_trials VALUES (%s,%s,%s::jsonb,%s::jsonb)',
                                 (campaign,slot,payload,outcome))
                conn.execute("""INSERT INTO bob_improvement_trials
                    SELECT %s,4,jsonb_build_object('valid',true,'ready',true,'adx',30,
                           'at',(extract(epoch FROM now())-30*60)*1000),NULL""",(campaign,))
                conn.execute('CREATE TABLE bob_precision_learning (id TEXT,state JSONB)')
                conn.execute("INSERT INTO bob_precision_learning VALUES ('private-identity','{\"phase\":\"validation\",\"lastAt\":1000}')")
                conn.commit()
                conn.execute('SET TRANSACTION READ ONLY')
                r=h.report(conn)
                self.assertEqual(r['items']['signals']['counts'],{'eligible':1})
                self.assertEqual(r['items']['signal-outcomes']['counts'],{'outcome-recorded':1})
                self.assertEqual(r['items']['improvement-trials']['counts'],{
                    'outcome-recorded': 1, 'trial-not-evaluable': 1,
                    'pending-horizon': 1, 'outcome-not-recorded': 1})
                # A fresh, not-yet-due outcome is pending rather than missing.
                # Only an overdue unrecorded decision is a real evidence gap.
                conn.commit()
                conn.execute("INSERT INTO bob_decision_audit VALUES ('pending-id',now() - interval '30 minutes','{}')")
                conn.execute("INSERT INTO bob_decision_audit VALUES ('overdue-id',now() - interval '75 minutes','{}')")
                conn.commit()
                conn.execute('SET TRANSACTION READ ONLY')
                horizons = h.report(conn)['items']['signal-outcomes']['counts']
                self.assertEqual(horizons, {
                    'outcome-recorded': 1, 'pending-horizon': 1, 'outcome-not-recorded': 1})
                self.assertEqual(r['items']['ranking-EUR']['counts'],{'incomplete':1})
                self.assertEqual(r['items']['ranking-CHF']['counts'],{'comparable':1})
                for slot,payload in enumerate([
                    {'marketReady':False,'candidates':[]},
                    {'marketReady':True,'candidates':[]},
                    {'marketReady':True,'candidates':[{}]},
                    {'marketReady':True,'candidates':[],'missing':['private-isin']},
                ],2000):
                    # Separate write transaction; probes themselves remain read-only.
                    conn.commit()
                    conn.execute('INSERT INTO bob_ranking_samples VALUES (%s,%s,%s::jsonb,%s::jsonb)',
                        ('EUR',slot,json.dumps({'complete':False}),json.dumps(payload)))
                conn.commit()
                conn.execute('SET TRANSACTION READ ONLY')
                details=h.report(conn)
                self.assertEqual(details['items']['ranking-EUR']['counts'],{
                    'incomplete':1,'market-not-ready':1,'no-comparable-products':1,
                    'insufficient-comparison-products':1,'entry-evidence-missing':1})
                self.assertNotIn('private-isin',json.dumps(details))
                self.assertEqual(r['items']['price-correction-states']['counts'],{'validation':1})
                self.assertNotIn('secret-id',json.dumps(r))
                self.assertNotIn('private-identity',json.dumps(r))
                conn.commit()
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

