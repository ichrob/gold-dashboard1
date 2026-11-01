"""PostgreSQL physical allocation versus bounded 24h writes, no source mutation."""
import json
import os
import unittest
import uuid
from unittest.mock import Mock

import storage_forensics as forensic


class DailyTrendTests(unittest.TestCase):
    def row(self, slot, size, counts=None):
        name='bob_diagnostic_history'
        return (slot, 500000, {name:size},
                {name:counts} if counts is not None else {})

    def test_exact_near_day_pair_not_oldest_multiday_rate(self):
        # First snapshot is 5 days old; nearest 24h pair takes priority.
        before={'inserted':200,'updated':30,'deleted':10,'hotUpdated':12}
        after={'inserted':250,'updated':45,'deleted':16,'hotUpdated':19}
        rows=[self.row(5*86400,2500,after),
              self.row(4*86400,1500,before),
              self.row(0,100,{'inserted':1,'updated':1,
                              'deleted':0,'hotUpdated':0})]
        result=forensic.daily(rows)
        self.assertEqual(result['status'],'observed')
        self.assertEqual(result['elapsedSeconds'],86400)
        entry=result['tables'][0]
        self.assertEqual(entry['netAllocatedBytes'],1000)
        self.assertEqual(entry['writeCounters'],{
            'inserted':50,'updated':15,'deleted':6,'hotUpdated':7})
        self.assertEqual(result['writeCountersStatus'],'observed')
        self.assertIsNone(result['diskBytesFreed'])
        self.assertNotIn('bloatBytes',result)

    def test_no_valid_window_cannot_invent_daily_trend(self):
        result=forensic.daily([self.row(0,10),self.row(5*86400,20)])
        self.assertEqual(result['status'],'needs-24h-pair')
        self.assertEqual(result['tables'],[])

    def test_earlier_size_only_snapshots_are_usable_but_not_write_proof(self):
        result=forensic.daily([self.row(86400,200),self.row(0,150)])
        self.assertEqual(result['tables'][0]['netAllocatedBytes'],50)
        self.assertEqual(result['writeCountersStatus'],'needs-two-counter-snapshots')
        self.assertIsNone(result['tables'][0]['writeCounters'])

    def test_stats_reset_never_reports_negative_write_activity(self):
        before={'inserted':100,'updated':50,'deleted':5,'hotUpdated':40}
        after={'inserted':10,'updated':1,'deleted':0,'hotUpdated':1}
        result=forensic.daily([self.row(86400,250,after),
                               self.row(0,200,before)])
        self.assertEqual(result['writeCountersStatus'],'counter-reset-or-wrap')
        self.assertEqual(result['tables'][0]['counterState'],'counter-reset-or-wrap')
        self.assertIsNone(result['tables'][0]['writeCounters'])

    def test_counter_values_fail_closed_on_boolean_and_negative(self):
        old={'inserted':0,'updated':0,'deleted':0,'hotUpdated':0}
        for bad in (True,-1,'secret'):
            with self.subTest(bad=bad):
                new={**old,'inserted':bad}
                v=forensic.daily([self.row(86400,100,new),self.row(0,100,old)])
                self.assertIsNone(v['tables'][0]['writeCounters'])
                self.assertEqual(v['writeCountersStatus'],'needs-two-counter-snapshots')
                self.assertNotIn('secret',json.dumps(v))

    def test_only_allowlisted_names_are_returned(self):
        bad=(86400,1000,{'private_credentials':9000}, {})
        old=(0,1000,{'private_credentials':0}, {})
        result=forensic.daily([bad,old])
        self.assertEqual(result['status'],'no-common-relations')
        self.assertNotIn('private_credentials',json.dumps(result))

    def test_bounded_metadata_snapshot_without_raw_rows(self):
        class Cursor:
            def fetchall(self):
                return [('bob_diagnostic_history',12,3,2,1),
                        ('private_account_table',999,999,999,999)]
        class Conn:
            def __init__(self):self.calls=[]
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,args=None):
                self.calls.append((sql,args))
                return Cursor()
        c=Conn()
        snapshot=forensic.snapshot_counters(c)
        self.assertEqual(snapshot,{'bob_diagnostic_history':{
            'inserted':12,'updated':3,'deleted':2,'hotUpdated':1}})
        self.assertEqual(c.calls[0][1][0],list(forensic.WATCHED))
        self.assertIn('LIMIT 10',c.calls[0][0])
        self.assertNotIn('private_account_table',str(snapshot))
        self.assertLessEqual(len(snapshot),10)

    def test_forensics_report_failure_is_not_bloat_or_disk_claim(self):
        class Conn:
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,*_):raise RuntimeError('secret source value')
        result=forensic.report(Conn(),[])
        self.assertEqual(result['status'],'not-observed')
        self.assertIsNone(result['reclaimableBytes'])
        self.assertFalse(result['rebuildAuthorized'])
        self.assertNotIn('secret source',json.dumps(result))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'PostgreSQL CI integration')
class PostgresForensicTests(unittest.TestCase):
    def test_catalog_is_read_only_and_reports_heap_index_and_toast(self):
        import psycopg
        from psycopg.types.json import Jsonb
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        name='forensics_'+uuid.uuid4().hex
        with psycopg.connect(dsn,autocommit=True) as c:
            c.execute('CREATE SCHEMA '+name)
            try:
                c.execute('SET search_path TO '+name)
                c.execute('CREATE TABLE bob_diagnostic_history (id integer PRIMARY KEY, payload jsonb NOT NULL)')
                for i in range(5):
                    c.execute('INSERT INTO bob_diagnostic_history VALUES (%s,%s)',
                              (i,Jsonb({'private':'never expose this value','value':i})))
                before=c.execute('SELECT id,payload FROM bob_diagnostic_history ORDER BY id').fetchall()
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    report=forensic.report(c,[])
                    counters=forensic.snapshot_counters(c)
                self.assertEqual(report['status'],'observed')
                t=next(x for x in report['layout']
                       if x['table']=='bob_diagnostic_history')
                self.assertGreater(t['totalBytes'],0)
                self.assertLessEqual(t['heapBytes']+t['indexBytes']+t['toastBytes'],t['totalBytes'])
                self.assertGreaterEqual(t['freeSpaceMapBytes'],0)
                self.assertGreaterEqual(t['visibilityMapBytes'],0)
                self.assertIsNone(report['reclaimableBytes'])
                self.assertFalse(report['rebuildAuthorized'])
                self.assertIn('bob_diagnostic_history',counters)
                self.assertNotIn('never expose this value',json.dumps(report))
                self.assertEqual(c.execute('SELECT id,payload FROM bob_diagnostic_history ORDER BY id').fetchall(),before)
            finally:
                c.execute('DROP SCHEMA '+name+' CASCADE')



class RecentAllocationTests(unittest.TestCase):
    def test_two_and_six_hour_windows_use_real_slots(self):
        before = {
            'bob_diagnostic_history': 400,
            'bob_android_list_images': 100,
            'bob_metric_checks': 300,
            'bob_oauth_secret': 50,
        }
        middle = {**before, 'bob_diagnostic_history': 460,
                  'bob_android_list_images': 120}
        latest = {**middle, 'bob_diagnostic_history': 480,
                  'bob_android_list_images': 150,
                  'bob_metric_checks': 250, 'bob_oauth_secret': 900}
        samples = [
            (21600, 1600, latest, {}),
            (14400, 1300, middle, {}),
            (0, 1000, before, {}),
        ]
        windows = forensic.recent_windows(samples)
        two = windows['twoHours']
        six = windows['sixHours']
        self.assertEqual(two['status'], 'observed')
        self.assertEqual(two['elapsedSeconds'], 7200)
        self.assertEqual(two['databaseBytesDelta'], 300)
        self.assertEqual(six['elapsedSeconds'], 21600)
        self.assertEqual(six['databaseBytesDelta'], 600)
        self.assertEqual(six['commonRelationBytesDelta'], 930)
        self.assertIn({'table':'bob_android_list_images','allocatedBytesDelta':50},
                      two['growingTables'])
        self.assertIn({'table':'bob_metric_checks','allocatedBytesDelta':-50},
                      two['shrinkingTables'])
        self.assertNotIn('bob_oauth_secret',str(windows))
        self.assertIsNone(two['diskBytesFreed'])
        self.assertNotIn('physicalVolumeBytesDelta',two)

    def test_missing_window_is_not_fabricated_from_multi_day_snapshot(self):
        windows = forensic.recent_windows([(86400,300,{'bob_metric_checks':300}),
                                           (0,100,{'bob_metric_checks':100})])
        self.assertEqual(windows['twoHours']['status'],'needs-snapshots')
        self.assertEqual(windows['sixHours']['status'],'needs-snapshots')
        self.assertIsNone(windows['twoHours']['diskBytesFreed'])

    def test_new_and_disappeared_relations_are_not_counted_as_zero(self):
        windows = forensic.recent_windows([
            (7200, 550, {'bob_diagnostic_history':200,'bob_new_table':200}),
            (0, 400, {'bob_diagnostic_history':100,'bob_old_table':300}),
        ])
        two = windows['twoHours']
        self.assertEqual(two['commonRelationBytesDelta'],100)
        self.assertEqual(two['comparableRelations'],1)
        self.assertEqual(two['nonComparableRelations'],2)
        self.assertEqual(two['growingTables'],[
            {'table':'bob_diagnostic_history','allocatedBytesDelta':100}
        ])
        self.assertEqual(windows['sixHours']['status'],'needs-snapshots')

    def test_twelve_entries_max_and_bad_types_rejected(self):
        old={'bob_table_'+str(i):100 for i in range(20)}
        new={'bob_table_'+str(i):150+i for i in range(20)}
        old.update({'bob_settings':100,'bob_x-unsafe':10})
        new.update({'bob_settings':10000,'bob_x-unsafe':10000,
                    'bob_invalid_boolean':True})
        two=forensic.recent_windows([
            (7200,1000,new),
            (0,800,old),
        ])['twoHours']
        self.assertEqual(len(two['growingTables']),12)
        self.assertEqual(two['truncatedGrowingCount'],8)
        self.assertNotIn('bob_settings',json.dumps(two))
        self.assertNotIn('bob_x-unsafe',json.dumps(two))
        self.assertEqual(two['nonComparableRelations'],1)
        self.assertEqual(two['status'],'observed')

    def test_no_valid_snapshots_do_not_claim_space(self):
        out=forensic.recent_windows([])
        self.assertEqual(out['twoHours']['status'],'needs-snapshots')
        self.assertEqual(out['sixHours']['status'],'needs-snapshots')
        self.assertIsNone(out['twoHours']['diskBytesFreed'])


if __name__=='__main__':
    unittest.main()
