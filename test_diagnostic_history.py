import json
import os
import threading
import time
import unittest
from unittest.mock import patch
import diagnostic_history as h
import background_push

class HistoryTests(unittest.TestCase):
    def event(self,**kw):
        return dict(id='a'*32,traceId='b'*32,decisionId='c'*32,stage='analysis',at=time.time(),
                    payload={'timeframe':'15m','result':{'direction':'NEUTRAL','decisionReason':'password=secret','analysisSnapshot':{'R':49},'token':'private'}},**kw)

    def test_projection_excludes_secrets_and_preserves_wait_decision(self):
        e=h.validate(self.event())
        self.assertEqual(e['payload']['result']['direction'],'NEUTRAL')
        self.assertEqual(e['payload']['result']['analysisSnapshot']['R'],49)
        self.assertNotIn('secret',json.dumps(e));self.assertNotIn('private',json.dumps(e))

    def test_trace_shared_across_services_not_settings(self):
        bundle={'spots':{'spot_price_as_of':'2026-10-19T10:00:00Z','xaus':4000},'fetched_at':5}
        self.assertEqual(h.trace(bundle),h.trace({**bundle,'history':{'bars_by_tf':{}},'learningPolicy':{}}))
        self.assertNotEqual(h.trace(bundle),h.trace({**bundle,'fetched_at':6}))

    def test_rejected_ids_times_and_stage(self):
        for key,value in [('stage','orders'),('traceId','private'),('at',float('nan')),('at',0)]:
            e=self.event();e[key]=value
            with self.assertRaises(ValueError):h.validate(e)

    def test_analysis_and_failure_have_correlated_evidence(self):
        with patch.object(h,'emit') as emit,patch.object(background_push,'_analyze',return_value={'direction':'NEUTRAL'}) as run:
            result=background_push.analyze({}, {'timeframe':'5m'})
            self.assertEqual(run.call_count,1)
            self.assertEqual([c.args[0] for c in emit.call_args_list],['input','analysis'])
            self.assertTrue(all(c.args[1]==result['traceId'] and c.args[3]==result['decisionId'] for c in emit.call_args_list))
        with patch.object(h,'emit') as emit,patch.object(background_push,'_analyze',side_effect=TimeoutError('private secret')):
            with self.assertRaises(TimeoutError):background_push.analyze({}, {})
            self.assertEqual(emit.call_args.args[0],'analysis-failed')
            self.assertNotIn('secret',str(emit.call_args))

    def test_weekend_pause_running_flags_never_mark_repair_healthy(self):
        health = {
            'status': 'ok',
            'automaticCollection': {'enabled': True, 'running': True,
                                    'state': 'paused',
                                    'lastCycleAt': time.time()-1000},
            'fibonacciMonitor': {'configured': True, 'status': 'paused',
                                 'lastSuccessAt': time.time()-1000},
            'strategyResearch': {'enabled': True, 'running': True,
                                 'phase': 'starting'},
            'auxiliaryWorkers': {},
            'repairSupervision': {'state': 'starting'},
        }
        with patch.object(h, 'emit') as output, \
             patch.object(background_push, 'degiro_session', return_value='weekend'):
            h.health(health)
        stored = output.call_args.args[2]
        self.assertEqual(stored['evidenceVersion'], 2)
        self.assertEqual(stored['goodCodes'], [])
        self.assertNotIn('background-worker-stopped', stored['goodCodes'])
        self.assertNotIn('market-worker-stopped', stored['goodCodes'])

    def test_original_cycle_clocks_and_provider_source_are_independent(self):
        now = time.time()
        health = {
            'status': 'ok',
            'automaticCollection': {'enabled': True, 'running': True,
                'state': 'ready', 'lastCycleAt': now-3,
                'cfdFeed': {'state': 'stale', 'successfulAt': now-2,
                            'sourceAt': 'not-an-original-clock'}},
            'fibonacciMonitor': {'configured': True, 'status': 'active',
                                 'lastSuccessAt': now-2},
            'strategyResearch': {'enabled': True, 'running': True,
                                 'phase': 'already-stored',
                                 'lastSuccessAt': (now-4)*1000},
            'auxiliaryWorkers': {
                'comparison-worker-stopped': {
                    'running': True, 'state':'loaded',
                    'successfulAt': now-3, 'archiveStatus': 'loaded'}},
            'repairSupervision': {'state':'ok','running':True,
                                  'lastCompletedAgeSeconds':2},
        }
        with patch.object(h, 'emit') as output, \
             patch.object(background_push, 'degiro_session', return_value='trading'):
            h.health(health)
        row = output.call_args.args[2]
        self.assertIn('market-worker-stopped', row['goodCodes'])
        self.assertIn('background-worker-stopped', row['goodCodes'])
        self.assertIn('research-worker-stopped', row['goodCodes'])
        self.assertIn('comparison-worker-stopped', row['goodCodes'])
        self.assertNotIn('market-feed-not-current', row['goodCodes'])
        self.assertNotIn('password', json.dumps(row))

    def test_source_clock_requires_valid_original_and_not_weekend_cached_tick(self):
        t = time.time()
        for bad in (None, True, float('nan'), float('inf'), t+10, t-1200,
                    '2026-10-25T15:00:00', 'not-a-clock', [],
                    str(t), '2035-10-25T11:00:00+00:00'):
            with self.subTest(value=str(bad)):
                self.assertFalse(h._recent_original_success(bad, t))
        self.assertTrue(h._recent_original_success(t-10,t))
        self.assertTrue(h._recent_original_success((t-10)*1000,t))
        from datetime import datetime, timezone
        self.assertTrue(h._recent_original_success(
            datetime.fromtimestamp(t-10,timezone.utc).isoformat(),t))

    def test_queue_bounded_without_blocking_io(self):
        from collections import deque
        with patch.object(h,'_QUEUE',deque(maxlen=2)),patch.object(h,'_RUNNING',True):
            for _ in range(4):h.emit('input','a'*32,{})
            self.assertEqual(len(h._QUEUE),2)

    def test_prune_timeout_does_not_discard_current_event(self):
        from contextlib import nullcontext

        class Conn:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))

            def transaction(self):
                return nullcontext()

        conn = Conn()
        with patch.object(h, 'prune', side_effect=TimeoutError('maintenance timeout')), \
             patch.object(h.time, 'monotonic', return_value=1801), \
             patch.object(h, '_LAST_PRUNE', 0):
            h.write(conn, self.event())

        self.assertTrue(conn.statements)
        self.assertIn('INSERT INTO bob_diagnostic_history', conn.statements[0][0])
        self.assertTrue(any("SET LOCAL statement_timeout='5s'" in sql for sql,_ in conn.statements))

    def test_new_process_defers_retention_until_first_full_interval(self):
        class Conn:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))

        conn = Conn()
        with patch.object(h, 'prune') as prune, \
             patch.object(h.time, 'monotonic',
                          return_value=h._LAST_PRUNE+h._PRUNE_INTERVAL_SECONDS-1):
            h.write(conn, self.event())

        prune.assert_not_called()
        self.assertTrue(conn.statements)
        self.assertIn('INSERT INTO bob_diagnostic_history', conn.statements[0][0])

    def test_parallel_prune_is_skipped_without_discarding_current_event(self):
        from contextlib import nullcontext

        class Conn:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))

            def transaction(self):
                return nullcontext()

        conn = Conn()
        prune_lock = threading.Lock()
        prune_lock.acquire()
        try:
            with patch.object(h, '_PRUNE_LOCK', prune_lock), \
                 patch.object(h, 'prune') as prune, \
                 patch.object(h.time, 'monotonic', return_value=1801), \
                 patch.object(h, '_LAST_PRUNE', 0):
                h.write(conn, self.event())
        finally:
            prune_lock.release()

        prune.assert_not_called()
        self.assertTrue(conn.statements)
        self.assertIn('INSERT INTO bob_diagnostic_history', conn.statements[0][0])

    def test_database_advisory_lock_prevents_cross_service_prune_collision(self):
        class Result:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class Conn:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))
                return Result((False,))

        conn = Conn()
        self.assertEqual(h.prune(conn), 0)
        self.assertEqual(len(conn.statements), 1)
        self.assertIn('pg_try_advisory_xact_lock', conn.statements[0][0])
        self.assertFalse(any('DELETE FROM bob_diagnostic_history' in sql
                             for sql, _ in conn.statements))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_retention_deletes_bounded_batches_and_preserves_recent_rows(self):
        import psycopg
        schema = 'diag_prune_' + str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn)
            conn.execute("""INSERT INTO bob_diagnostic_history
                (id,trace_id,stage,observed_at,recorded_at,payload)
                SELECT i::text,'test','health',0,now()-interval '8 days','{}'::jsonb
                FROM generate_series(1,1200) i""")
            conn.execute("""INSERT INTO bob_diagnostic_history
                (id,trace_id,stage,observed_at,payload)
                VALUES ('recent','test','health',0,'{}'::jsonb)""")
            h.prune(conn)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_diagnostic_history').fetchone()[0],701)
            h.prune(conn)
            h.prune(conn)
            self.assertEqual(conn.execute('SELECT id FROM bob_diagnostic_history').fetchall(),[('recent',)])
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_legacy_health_running_and_weekend_good_codes_cannot_fake_repair(self):
        import psycopg
        import bob_repair_store
        schema = 'diag_proof_' + str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn)
            bob_repair_store.init(conn)
            conn.execute("""INSERT INTO bob_self_heal_events(
                event_id,event_at,kind,code)
                VALUES('test',now()-interval '20 minutes',
                       'repair-verified','background-worker-stopped')""")
            # Both old observations claimed good from mere paused/running
            # status, without an original clock proving completed work.
            for i, age in enumerate((600,30)):
                h.write(conn, {'id':f'{i:032x}', 'traceId':'b'*32,
                    'stage':'health', 'at':time.time()-age,
                    'payload':{'status':'ok', 'session':'weekend',
                               'goodCodes':['background-worker-stopped']}})
            old = h.report(conn)['repairFollowups'][0]
            self.assertEqual(old['state'], 'pending-or-stale')
            self.assertEqual(old['goodChecks'], 0)
            # Even with a new bad code, recurrence remains visible; it can
            # never be hidden by an older positive status.
            for i,age in enumerate((600,30),start=10):
                h.write(conn, {'id':f'{i:032x}', 'traceId':'b'*32,
                    'stage':'health', 'at':time.time()-age,
                    'payload':{'evidenceVersion':2,
                               'goodCodes':['background-worker-stopped']}})
            new = h.report(conn)['repairFollowups'][0]
            self.assertEqual(new['goodChecks'],2)
            self.assertEqual(new['state'],'observed-stable')
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_durable_restart_readonly_followup_and_recurrence(self):
        import psycopg
        import bob_repair_store
        schema='diag_test_'+str(time.time_ns())
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn);bob_repair_store.init(conn)
            conn.execute("INSERT INTO bob_self_heal_events(event_id,event_at,kind,code) VALUES('test',now()-interval '20 minutes','repair-verified','market-feed-not-current')")
            for i,age in enumerate((600,30)):
                h.write(conn,{'id':f'{i:032x}','traceId':'b'*32,'stage':'health','at':time.time()-age,
                    'payload':{'evidenceVersion':2,'goodCodes':['market-feed-not-current'],'badCodes':[]}})
        # New connection simulates a restarted reader. A read-only transaction must suffice.
        with psycopg.connect(dsn) as conn:
            conn.execute('SET search_path TO '+schema);conn.commit()
            conn.execute('SET TRANSACTION READ ONLY')
            report=h.report(conn)
            self.assertEqual(len(report['events']),2)
            self.assertEqual(report['repairFollowups'][0]['state'],'observed-stable')
        with psycopg.connect(dsn) as conn:
            conn.execute('SET search_path TO '+schema)
            event={'id':'f'*32,'traceId':'b'*32,'stage':'health','at':time.time(),'payload':{'badCodes':['market-feed-not-current']}}
            h.write(conn,event);h.write(conn,event)
            report=h.report(conn)
            self.assertEqual(len(report['events']),3)
            self.assertEqual(report['repairFollowups'][0]['state'],'recurred')
            conn.execute("DELETE FROM bob_diagnostic_history WHERE payload->'badCodes' ? 'market-feed-not-current'")
            conn.execute("INSERT INTO bob_self_heal_events(event_id,event_at,kind,code) VALUES('later',now()-interval '10 minutes','detected','market-feed-not-current')")
            report=h.report(conn)
            self.assertEqual(report['repairFollowups'][0]['state'],'recurred')
            self.assertEqual(report['repairFollowups'][0]['recordedRecurrences'],1)
            conn.execute('DROP SCHEMA '+schema+' CASCADE')
