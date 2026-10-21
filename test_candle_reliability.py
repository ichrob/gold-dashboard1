import copy
import json
import os
import time
import unittest
from unittest.mock import patch
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
        self.assertEqual(c.classify(self.rows(),'1m',time.time()+600),'stale')
    def test_archive_failure_cannot_break_source_observation(self):
        with patch.object(c,'request',side_effect=OSError('offline')) as req:
            c.observe('biquote','1m',self.rows())
            req.assert_not_called()
        self.assertTrue(c._ROWS)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
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
