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


    def test_prune_log_identifies_sanitized_failed_stage(self):
        from contextlib import nullcontext

        class Conn:
            def execute(self, sql, params=()):
                return None

            def transaction(self):
                return nullcontext()

        error = h._PruneStageError('cap-delete',
                                   TimeoutError('private database detail'))
        with patch.object(h, 'prune', side_effect=error), \
             patch.object(h.time, 'monotonic', return_value=1801), \
             patch.object(h, '_LAST_PRUNE', 0), \
             patch('builtins.print') as output:
            h.write(Conn(), self.event())

        line = output.call_args.args[0]
        self.assertIn('stage=cap-delete', line)
        self.assertIn('error=TimeoutError', line)
        self.assertNotIn('private database detail', line)

    def test_prune_stage_errors_distinguish_age_and_cap_deletes(self):
        class Result:
            rowcount = 0

            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Conn:
            def __init__(self, failing_stage):
                self.failing_stage = failing_stage

            def execute(self, sql, params=()):
                if 'pg_try_advisory_xact_lock' in sql:
                    return Result((True,))
                if "interval '7 days'" in sql:
                    stage = 'age-delete'
                elif 'SELECT count(*)' in sql:
                    stage = 'cap-count'
                else:
                    stage = 'cap-delete'
                if stage == self.failing_stage:
                    raise TimeoutError('private database detail')
                if stage == 'cap-count':
                    return Result((60001,))
                return Result()

        for stage in ('age-delete', 'cap-count', 'cap-delete'):
            with self.subTest(stage=stage):
                with self.assertRaises(h._PruneStageError) as caught:
                    h.prune(Conn(stage))
                self.assertEqual(caught.exception.stage, stage)
                self.assertEqual(caught.exception.error_type, 'TimeoutError')
                self.assertNotIn('private database detail',
                                 str(caught.exception))

    def test_cap_delete_avoids_offset_and_uses_exact_bounded_excess(self):
        class Result:
            rowcount = 0

            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Conn:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))
                if 'pg_try_advisory_xact_lock' in sql:
                    return Result((True,))
                if 'SELECT count(*)' in sql:
                    return Result((60550,))
                return Result()

        conn = Conn()
        h.prune(conn)
        cap_sql, cap_params = next(
            (sql, params) for sql, params in conn.statements
            if 'DELETE FROM bob_diagnostic_history' in sql
            and "interval '7 days'" not in sql)
        self.assertNotIn('OFFSET', cap_sql)
        self.assertIn('ORDER BY recorded_at ASC', cap_sql)
        self.assertIn('LIMIT %s', cap_sql)
        self.assertEqual(cap_params, (500,))
        self.assertEqual(h._PRUNE_CAP_BATCH_SIZE, 500)
        self.assertEqual(h._PRUNE_MAX_EVENTS, 60000)

    def test_cap_delete_skips_at_exact_limit(self):
        class Result:
            rowcount = 0

            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class Conn:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=()):
                self.statements.append((sql, params))
                if 'pg_try_advisory_xact_lock' in sql:
                    return Result((True,))
                if 'SELECT count(*)' in sql:
                    return Result((60000,))
                return Result()

        conn = Conn()
        h.prune(conn)
        cap_deletes = [sql for sql, _ in conn.statements
                       if 'DELETE FROM bob_diagnostic_history' in sql
                       and "interval '7 days'" not in sql]
        self.assertEqual(cap_deletes, [])

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
    def test_archive_reads_explicitly_refuse_old_rows_if_prune_is_delayed(self):
        """A late retention sweep cannot expose older-than-seven-day samples."""
        import psycopg
        import bob_repair_store
        schema='diag_seven_days_'+str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn)
            bob_repair_store.init(conn)
            rows=[
                ('old', "now()-interval '8 days'"),
                ('kept', "now()-interval '6 days'"),
                ('recent', "now()"),
            ]
            for key, clock in rows:
                conn.execute("""INSERT INTO bob_diagnostic_history
                    (id,trace_id,stage,observed_at,recorded_at,payload)
                    VALUES (%s,%s,'health',extract(epoch FROM """+clock+"""),
                            """+clock+""",'{}'::jsonb)""", (key,'a'*32))
            report=h.report(conn)
            event_ids=[e['id'] for e in report['events']]
            self.assertNotIn('old', event_ids)
            self.assertEqual(set(event_ids),{'kept','recent'})
            # The raw old record was still present and not rewritten by read.
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM bob_diagnostic_history").fetchone()[0],3)
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_durable_history_includes_original_paper_input_and_push_delivery(self):
        """Newly sampled stages are SELECT-only, bounded and privacy projected."""
        import psycopg
        import bob_repair_store
        schema='diag_extra_stages_'+str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn)
            bob_repair_store.init(conn)
            for i in range(23):
                h.write(conn, {
                    'id':f'{i+100:032x}', 'traceId':'a'*32,
                    'stage':'push-delivery', 'at':time.time()-23+i,
                    'payload':{'outcome':'provider-accepted',
                               'httpStatus':201,'direction':'LONG',
                               'test':True,'synthetic':True,
                               'deviceToken':'DO-NOT-PUBLISH',
                               'phoneNumber':'PRIVATE'}})
                h.write(conn, {
                    'id':f'{i+200:032x}', 'traceId':'a'*32,
                    'stage':'paper-input', 'at':time.time()-23+i,
                    'payload':{'phase':'checked','checkedAt':time.time()-23+i,
                               'profiles':[{'profile':'balanced',
                                            'outcome':'not-verified',
                                            'ready':False, 'priceFresh':False,
                                            'price':'SECRET-QUOTE'}],
                               'account':'PRIVATE-ACCOUNT'}})
            # Close the writer transaction, then prove the report works
            # under a separate PostgreSQL READ ONLY transaction.
            conn.commit()
            with conn.transaction():
                conn.execute('SET TRANSACTION READ ONLY')
                sample=h.report(conn)
            selected=[e for e in sample['events'] if e['stage'] in
                      ('push-delivery','paper-input')]
            coverage=sample['stageCoverage']
            self.assertEqual(coverage['status'],'observed')
            self.assertEqual(coverage['totalSampled'],40)
            self.assertEqual(coverage['counts']['push-delivery'],20)
            self.assertEqual(coverage['counts']['paper-input'],20)
            self.assertEqual(len(coverage['counts']),len(h.STAGES))
            self.assertFalse(coverage['handsetDeliveryVerified'])
            self.assertFalse(coverage['paperExecutionVerified'])
            self.assertNotIn('PRIVATE',json.dumps(coverage))
            self.assertEqual(len(selected),40)
            self.assertEqual(sum(e['stage']=='push-delivery' for e in selected),20)
            self.assertEqual(sum(e['stage']=='paper-input' for e in selected),20)
            self.assertTrue(all(e['stage'] in h.STAGES for e in selected))
            serialized=json.dumps(sample)
            self.assertNotIn('DO-NOT-PUBLISH', serialized)
            self.assertNotIn('SECRET-QUOTE', serialized)
            self.assertNotIn('PRIVATE-ACCOUNT', serialized)
            self.assertIn('provider-accepted', serialized)
            self.assertIn('paper-input', serialized)
            self.assertIn('push-delivery', serialized)
            self.assertNotIn('delivered-to-device', serialized)
            self.assertTrue(sample['scope'].startswith('sampled'))
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_seven_day_read_window_excludes_pre_retention_record(self):
        """An old unpruned event must never appear in a bounded archive read."""
        import psycopg
        import bob_repair_store
        schema = 'diag_history_window_' + str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn)
            bob_repair_store.init(conn)
            # Do not depend on background prune: read must itself enforce 7d.
            conn.execute("""INSERT INTO bob_diagnostic_history
                (id,trace_id,stage,observed_at,recorded_at,payload)
                VALUES (%s,%s,'health',%s,now()-interval '8 days',%s::jsonb)""",
                ('a'*32,'b'*32,time.time()-8*86400,'{"status":"ok","session":"weekend","badCodes":[]}'))
            conn.execute("""INSERT INTO bob_diagnostic_history
                (id,trace_id,stage,observed_at,recorded_at,payload)
                VALUES (%s,%s,'health',%s,now(),%s::jsonb)""",
                ('c'*32,'b'*32,time.time(),'{"status":"ok","session":"weekend","badCodes":[]}'))
            conn.commit()
            with conn.transaction():
                conn.execute('SET TRANSACTION READ ONLY')
                report=h.report(conn)
            self.assertEqual(report['stageCoverage']['counts']['health'],1)
            self.assertEqual(report['stageCoverage']['totalSampled'],1)
            self.assertEqual(len(report['events']),1)
            self.assertEqual(report['events'][0]['id'],'c'*32)
            self.assertFalse(report['stageCoverage']['handsetDeliveryVerified'])
            self.assertFalse(report['stageCoverage']['paperExecutionVerified'])
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

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

    def test_journal_prune_stays_outside_hot_five_minute_write_path(self):
        """A failed best-effort prune must not be retried every five minutes."""
        import inspect
        self.assertGreaterEqual(h._PRUNE_INTERVAL_SECONDS, 1800)
        source = inspect.getsource(h)
        self.assertIn('_LAST_PRUNE = time.monotonic()', source.splitlines())
        self.assertNotIn('_LAST_PRUNE = time.monotonic() - 240', source)

    def test_journal_cap_catches_up_without_deleting_source_evidence(self):
        import psycopg
        schema = 'diag_cap_' + str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            h.init(conn)
            conn.execute("CREATE TABLE bob_spot_observations (price numeric)")
            conn.execute("INSERT INTO bob_spot_observations VALUES (4000)")
            conn.execute("""INSERT INTO bob_diagnostic_history
                (id,trace_id,stage,observed_at,recorded_at,payload)
                SELECT i::text,'test','health',0,
                    now()-i*interval '1 second','{}'::jsonb
                FROM generate_series(1,65000) i""")
            expected = list(range(64500,59999,-500)) + [60000]
            for remaining in expected:
                h.prune(conn)
                self.assertEqual(conn.execute(
                    'SELECT count(*) FROM bob_diagnostic_history').fetchone()[0],remaining)
            self.assertEqual(conn.execute(
                'SELECT min(id::int),max(id::int) FROM bob_diagnostic_history'
                ).fetchone(),(1,60000))
            self.assertEqual(conn.execute(
                'SELECT price FROM bob_spot_observations').fetchone()[0],4000)
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
