import copy
import json
import os
import time
import unittest
from unittest.mock import patch, MagicMock
import candle_reliability as c
import server
from test_ema200_history_backfill import candle_series,xaus_points

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        for name in ('_ROWS','_CHECKS','_STATS','_SAVED'):
            p=patch.object(c,name,{});p.start();self.addCleanup(p.stop)
        for name in ('_technical_history','_ema_backfill_series','_ema_backfill_attempted'):
            p=patch.object(server,name,{});p.start();self.addCleanup(p.stop)
    def rows(self,n=220):
        rows=candle_series(n,step=60000)
        for b in rows:b['source']=c.SOURCES['biquote']
        return rows
    def test_archive_rejects_changed_instrument_source_estimates_open_and_invalid(self):
        rows=self.rows()
        self.assertEqual(len(c.validated('biquote/1m',rows)),220)
        for field,value in [('instrument','GC=F'),('source',c.SOURCES['xaus']),('estimated',True),('providerIsOpen',True),('close',float('nan')),('openTime',time.time()*1000+60000)]:
            bad=copy.deepcopy(rows);bad[-1][field]=value
            with self.assertRaises(ValueError):c.validated('biquote/1m',bad)
    def test_retains_source_history_without_filling_internal_gaps(self):
        rows=self.rows()
        c.observe('biquote','1m',rows)
        current=rows[-100:];current.pop(-5)
        c.observe('biquote','1m',current)
        self.assertEqual(len(c._ROWS['biquote/1m']),219)
        c.observe('xaus','1m',rows)
        self.assertNotIn('xaus/1m',c._ROWS)
    def test_stale_original_clock_remains_stale_after_restart(self):
        rows=self.rows()
        for b in rows:b['openTime']-=600000
        def request(action,payload):return {'statistics':{}} if payload['key']=='statistics' else {'rows':rows if payload['key']=='biquote/1m' else []}
        import technical_candles
        with patch.object(c,'request',side_effect=request),patch.dict(technical_candles._cache,{},clear=True):
            c.restore(server)
            self.assertEqual(server.retain_technical_history('1m',[]),c.validated('biquote/1m',rows))
            self.assertEqual(c.classify(server.retain_technical_history('1m',[]),'1m',time.time()),'stale')
            self.assertEqual(technical_candles._cache['1m'][0],0)
    def test_standby_warms_while_primary_is_healthy(self):
        rows=self.rows()
        for b in rows:b['source']=c.SOURCES['xaus']
        with patch.object(server,'fetch_json',return_value={'points':xaus_points(rows)}) as fetch:
            server._ema200_history_backfill('1m','',[],standby=True)
            server._ema200_history_backfill('1m','',[],standby=True)
        self.assertEqual(fetch.call_count,1)
        self.assertTrue(server._ema_backfill_series['1m'])
        self.assertIn('xaus/1m',c._ROWS)
    def test_failure_recovery_duration_and_unknown_restart_gap(self):
        row=c.transition(None,'current',100)
        row=c.transition(row,'stale',130)
        row=c.transition(row,'unavailable',160)
        row=c.transition(row,'current',190)
        self.assertEqual(row['incidents'],1)
        self.assertEqual(row['badSeconds'],60)
        row=c.transition(row,'current',500)
        self.assertEqual(row['unknownSeconds'],310)
        self.assertEqual(row['badSeconds'],60)
        row=c.transition(row,'paused',530)
        row=c.transition(row,'paused',560)
        self.assertEqual(row['incidents'],1)
    def test_empty_insufficient_stale_and_healthy_are_distinct(self):
        self.assertEqual(c.classify([],'1m',time.time()),'unavailable')
        self.assertEqual(c.classify(self.rows(20),'1m',time.time()),'incomplete')
        self.assertEqual(c.classify(self.rows(),'1m',time.time()),'current')
        wrong=self.rows();wrong[-1]['instrument']='GC=F'
        self.assertEqual(c.classify(wrong,'1m',time.time()),'incomplete')
        self.assertEqual(c.classify(self.rows(),'1m',time.time()+600),'stale')
    def test_archive_failure_cannot_break_source_observation(self):
        with patch.object(c,'request',side_effect=OSError('offline')) as req:
            c.observe('biquote','1m',self.rows())
            req.assert_not_called()
        self.assertTrue(c._ROWS)

    def test_failed_series_does_not_starve_later_series_or_statistics(self):
        first = self.rows()
        second = copy.deepcopy(first)
        for row in second:
            row['source'] = c.SOURCES['xaus']
        c._ROWS.update({'biquote/1m': first, 'xaus/1m': second})
        calls = []
        def request(action, payload):
            calls.append(payload['key'])
            if payload['key'] == 'biquote/1m':
                raise OSError('transient timeout')
            return {'ok': True}
        with patch.object(c, 'request', side_effect=request):
            with self.assertRaises(OSError):
                c.cycle(server)
        self.assertEqual(calls, ['biquote/1m', 'xaus/1m', 'statistics'])
        self.assertNotIn('biquote/1m', c._SAVED)
        self.assertEqual(len(c._SAVED['xaus/1m']), 32)
        with patch.object(c, 'request', return_value={'ok': True}) as req:
            c.cycle(server)
        self.assertEqual([call.args[1]['key'] for call in req.call_args_list],
                         ['biquote/1m', 'statistics'])

    def test_only_acknowledged_identical_candles_skip_write(self):
        c._ROWS['biquote/1m'] = self.rows()
        with patch.object(c, 'request', return_value={'ok': False}):
            with self.assertRaises(ValueError):
                c.cycle(server)
        self.assertNotIn('biquote/1m', c._SAVED)
        with patch.object(c, 'request', return_value={'ok': True}) as req:
            c.cycle(server)
            req.reset_mock()
            c.cycle(server)
            self.assertEqual([call.args[1]['key'] for call in req.call_args_list], ['statistics'])
            c._ROWS['biquote/1m'][-1]['high'] += 1
            req.reset_mock()
            c.cycle(server)
            self.assertEqual([call.args[1]['key'] for call in req.call_args_list],
                             ['biquote/1m', 'statistics'])

    def test_evidence_batches_preserve_all_rows_without_partial_commit(self):
        conn = MagicMock()
        rows = self.rows(600)
        c.handle(conn, 'write', {'key': 'biquote/1m', 'rows': rows})
        batches = [json.loads(call.args[1][1]) for call in conn.execute.call_args_list
                   if 'INSERT INTO bob_candle_evidence' in call.args[0]]
        self.assertEqual([len(batch) for batch in batches], [128, 128, 128, 128, 88])
        self.assertEqual([row for batch in batches for row in batch], c.validated('biquote/1m', rows))
        conn.commit.assert_not_called()
        conn.reset_mock()
        conn.execute.side_effect = [None, OSError('second batch failed')]
        with self.assertRaises(OSError):
            c.handle(conn, 'write', {'key': 'biquote/1m', 'rows': rows})
        self.assertFalse(any('INSERT INTO bob_candle_checkpoints' in call.args[0]
                             for call in conn.execute.call_args_list))
        conn.commit.assert_not_called()

    def test_evidence_statement_work_stays_below_observed_timeout_batch(self):
        conn = MagicMock()
        rows = self.rows(600)
        executed = []
        def execute(sql, params=None):
            if 'INSERT INTO bob_candle_evidence' in sql:
                batch = json.loads(params[1])
                executed.append(batch)
                if len(batch) > 128:
                    raise TimeoutError('simulated statement timeout under concurrent database load')
            return MagicMock()
        conn.execute.side_effect = execute
        c.handle(conn, 'write', {'key': 'biquote/1m', 'rows': rows})
        self.assertEqual([len(batch) for batch in executed], [128, 128, 128, 128, 88])
        self.assertEqual([row for batch in executed for row in batch],
                         c.validated('biquote/1m', rows))
        conn.commit.assert_not_called()

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_repeated_checkpoint_skips_insert_attempts_but_preserves_revisions(self):
        import psycopg
        schema='candle_delta_'+str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET search_path TO '+schema)
            c.init(conn)
            # BEFORE INSERT also fires for ON CONFLICT DO NOTHING. Count the
            # attempted writes, not just the final row count, to reproduce the
            # redundant write path on a mostly unchanged checkpoint.
            conn.execute('CREATE TABLE insert_attempts (n integer NOT NULL)')
            conn.execute('INSERT INTO insert_attempts VALUES (0)')
            conn.execute('''CREATE FUNCTION count_attempt() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                    UPDATE insert_attempts SET n=n+1;
                    RETURN NEW;
                END $$''')
            conn.execute('''CREATE TRIGGER count_attempt BEFORE INSERT
                ON bob_candle_evidence FOR EACH ROW EXECUTE FUNCTION count_attempt()''')
            rows=candle_series(600,step=60000)
            for row in rows:row['source']=c.SOURCES['biquote']
            def write(data):
                conn.execute('UPDATE insert_attempts SET n=0')
                c.handle(conn,'write',{'key':'biquote/1m','rows':data})
                return conn.execute('SELECT n FROM insert_attempts').fetchone()[0]
            self.assertEqual(write(rows),600)
            self.assertEqual(write(rows),0)
            changed=copy.deepcopy(rows)
            changed[-1]['high']+=1
            self.assertEqual(write(changed),1)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_candle_evidence').fetchone()[0],601)
            self.assertEqual(c.handle(conn,'read',{'key':'biquote/1m'})['rows'],
                             c.validated('biquote/1m',changed))
            # Returning an older known revision cannot discard either original.
            self.assertEqual(write(rows),0)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_candle_evidence').fetchone()[0],601)
            # A missing evidence row must be backfilled even if the checkpoint
            # already contains the same payload (e.g. an older installation).
            conn.execute('DELETE FROM bob_candle_evidence WHERE open_time=%s',(rows[0]['openTime'],))
            self.assertEqual(write(rows),1)
            # Checkpoint failure must roll back new evidence with it.
            conn.execute('''CREATE FUNCTION fail_checkpoint() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test rollback'; END $$''')
            conn.execute('''CREATE TRIGGER fail_checkpoint BEFORE INSERT OR UPDATE
                ON bob_candle_checkpoints FOR EACH ROW EXECUTE FUNCTION fail_checkpoint()''')
            newer=copy.deepcopy(rows)
            newer[-1]['high']+=2
            with self.assertRaises(psycopg.errors.RaiseException):
                with conn.transaction():
                    write(newer)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_candle_evidence').fetchone()[0],601)
            self.assertEqual(c.handle(conn,'read',{'key':'biquote/1m'})['rows'],
                             c.validated('biquote/1m',rows))
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_restart_archive_and_monitor_fence(self):
        import psycopg
        schema='candles_'+str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
            c.init(conn)
            rows=candle_series(220,step=60000)
            for b in rows:b['source']=c.SOURCES['biquote']
            c.handle(conn,'write',{'key':'biquote/1m','rows':rows})
            c.handle(conn,'write',{'key':'biquote/1m','rows':rows[:-1]})
            self.assertEqual(len(c.handle(conn,'read',{'key':'biquote/1m'})['rows']),220)
            now=time.time()
            def write(owner,state,at):
                return c.handle(conn,'write',{'key':'statistics','ownerStartedAt':owner,'statistics':{'analysis/1m':{'state':state,'checkedAt':at}}})
            write(now-100,'stale',now-60)
            recovered=write(now-50,'current',now-30)
            self.assertEqual(recovered['statistics']['analysis/1m']['badSeconds'],30)
            ignored=write(now-100,'stale',now)
            self.assertEqual(ignored['statistics']['analysis/1m']['state'],'current')
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('SET search_path TO '+schema)
            self.assertEqual(len(c.handle(conn,'read',{'key':'biquote/1m'})['rows']),220)
            self.assertEqual(c.handle(conn,'read',{'key':'statistics'})['statistics']['analysis/1m']['incidents'],1)
            conn.execute('DROP SCHEMA '+schema+' CASCADE')
