import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import patch
import cold_analysis as cold
import cold_analysis_candidate_scan as candidate_scan
from test_cold_metrics import Drive


class ProjectionTests(unittest.TestCase):
    def test_sql_projection_only_and_hot_passthrough(self):
        payload={'timeframe':'15m','purpose':'test','result':{'ready':False,'priceFresh':None,'dataAt':123,'details':[1,2]}}
        self.assertEqual(cold.projection(payload),{'timeframe':'15m','result':{'ready':False,'priceFresh':None,'dataAt':123}})
        self.assertIs(cold.resolve(None,payload,()),payload)
        self.assertEqual(cold.projection({'result':None}),{})


class ColdSchedulerIsolationTests(unittest.TestCase):
    def test_checked_offload_does_not_invoke_inline_vacuum(self):
        class EndCycle(Exception):
            pass

        sleeps = []

        def one_cycle(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise EndCycle()

        # Exercise the real loop body, but never start a worker or use a DB.
        with patch.dict(os.environ, {'BOB_COLD_ANALYSIS_ENABLED': '1'}), \
             patch.object(cold, '_THREAD', None), \
             patch.object(cold.threading, 'Thread') as thread:
            cold.start()
            thread.return_value.start.assert_called_once()
            target = thread.call_args.kwargs['target']

        with patch('archive_worker.status', return_value={'status': 'idle'}), \
             patch.object(cold, 'run_once', return_value={'status': 'checked', 'batches': []}) as run, \
             patch('storage_maintenance.run_once') as maintenance, \
             patch('storage_pressure.delay', return_value=900), \
             patch.object(cold.time, 'sleep', side_effect=one_cycle), \
             patch('builtins.print') as output:
            with self.assertRaises(EndCycle):
                target()

        run.assert_called_once()
        maintenance.assert_not_called()
        self.assertEqual(sleeps, [300, 900])
        self.assertIn('"status": "checked"', output.call_args.args[0])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        secret=patch.dict(os.environ, {'PUSH_SERVICE_TOKEN':'offline-cold-test-only-'+('x'*48)})
        secret.start()
        self.addCleanup(secret.stop)
        self.c=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True)
        self.schema='cold_analysis_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+self.schema)
        self.c.execute('SET search_path TO '+self.schema)
        self.c.execute('''CREATE TABLE bob_diagnostic_history(id text primary key,stage text,
            observed_at double precision,build text,recorded_at timestamptz,payload jsonb)''')
        cold.init(self.c);cold._LOCATION.clear();cold.codec._CACHE.clear()
        candidate_scan.commit_cursor(None)
        self.drive=Drive()
        self.payload={'timeframe':'15m','purpose':'original','result':{'ready':True,'priceFresh':False,'dataAt':123456,
            'details':[hashlib.sha256(str(i).encode()).hexdigest() for i in range(80)],'originalInteger':9007199254740993}}
        for key,stage,age in [('old','analysis','8 hours'),('hot','analysis','1 hour'),('input','input','8 hours')]:
            self.c.execute("INSERT INTO bob_diagnostic_history VALUES(%s,%s,123.25,NULL,now()-%s::interval,%s::jsonb)",(key,stage,age,json.dumps(self.payload)))

    def tearDown(self):
        self.c.execute('DROP SCHEMA '+self.schema+' CASCADE');self.c.close()

    def projection_rows(self):
        return self.c.execute("SELECT id,payload->>'timeframe',payload->'result'->>'ready',payload->'result'->>'priceFresh',payload->'result'->>'dataAt' FROM bob_diagnostic_history ORDER BY id").fetchall()

    def test_lossless_restart_sql_fields_and_lookup_after_retention(self):
        before=self.projection_rows()
        size_before=self.c.execute("SELECT pg_column_size(payload) FROM bob_diagnostic_history WHERE id='old'").fetchone()[0]
        result=cold.offload_batch(self.c,self.drive)
        self.assertEqual(result['movedRows'],1)
        self.assertTrue(all(blob.startswith(b'BOBCOLD1') for blob in self.drive.files.values()))
        self.assertEqual(before,self.projection_rows())
        self.assertIsNone(result['diskBytesFreed'])
        pointer=self.c.execute("SELECT payload FROM bob_diagnostic_history WHERE id='old'").fetchone()[0]
        self.assertIn(cold.TAG,pointer)
        self.assertLess(self.c.execute("SELECT pg_column_size(payload) FROM bob_diagnostic_history WHERE id='old'").fetchone()[0],size_before)
        for key in ('input','hot'):
            self.assertNotIn(cold.TAG,self.c.execute('SELECT payload FROM bob_diagnostic_history WHERE id=%s',(key,)).fetchone()[0])
        cold._LOCATION.clear();cold.codec._CACHE.clear()
        self.assertEqual(cold.get(self.c,'old',drive=self.drive),self.payload)
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):
            cold.resolve(self.c,pointer,('different','analysis',123.25,None),drive=self.drive)
        pointer['result']['ready']=False
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):
            cold.resolve(self.c,pointer,('old','analysis',123.25,None),drive=self.drive)
        self.c.execute("DELETE FROM bob_diagnostic_history WHERE id='old'")
        self.assertEqual(cold.get(self.c,'old',drive=self.drive),self.payload)
        self.assertEqual(cold.status(self.c)['offloadedRows'],1)

    def test_failed_download_preserves_source(self):
        self.drive.corrupt=True
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.offload_batch(self.c,self.drive)
        self.assertEqual(self.c.execute("SELECT payload FROM bob_diagnostic_history WHERE id='old'").fetchone()[0],self.payload)
        self.assertEqual(self.c.execute('SELECT count(*) FROM bob_cold_analysis_batches').fetchone()[0],0)

    def test_concurrent_edit_is_not_overwritten(self):
        def changed():
            self.c.execute("UPDATE bob_diagnostic_history SET payload='{}' WHERE id='old'")
        self.drive.on_upload=changed
        result=cold.offload_batch(self.c,self.drive)
        self.assertEqual(result['movedRows'],0)
        self.assertEqual(self.c.execute("SELECT payload FROM bob_diagnostic_history WHERE id='old'").fetchone()[0],{})

    def test_transaction_rollback_keeps_original(self):
        with patch.object(cold,'resolve',side_effect=RuntimeError('comparison failed')):
            with self.assertRaises(RuntimeError):cold.offload_batch(self.c,self.drive)
        self.assertEqual(self.c.execute("SELECT payload FROM bob_diagnostic_history WHERE id='old'").fetchone()[0],self.payload)
        self.assertEqual(self.c.execute('SELECT count(*) FROM bob_cold_analysis_batches').fetchone()[0],0)

    def test_corrupt_archive_read_fails_explicitly(self):
        cold.offload_batch(self.c,self.drive)
        cold.codec._CACHE.clear();self.drive.corrupt=True
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.get(self.c,'old',drive=self.drive)


    def test_bounded_scanner_skips_pointer_prefix_and_reaches_original(self):
        self.c.execute("""CREATE INDEX sample_analysis_age
            ON bob_diagnostic_history(stage,recorded_at DESC)""")
        pointer = json.dumps({cold.TAG: ["f" * 32, 0], "timeframe": "15m"})
        rows = [
            ("arch-" + str(i), "analysis", 123.0, None, pointer, i)
            for i in range(900)
        ]
        with self.c.cursor() as cur:
            cur.executemany("""INSERT INTO bob_diagnostic_history
            (id,stage,observed_at,build,payload,recorded_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,
                    now()-interval '12 hours'+(%s*interval '1 second'))""", rows)
        result = cold.offload_batch(self.c, self.drive)
        self.assertEqual(result["status"], "verified-offload")
        self.assertEqual(result["movedRows"], 1)
        self.assertTrue(result["candidateScanBounded"])
        self.assertGreater(result["scannedRows"], 900)
        self.assertLessEqual(result["scannedRows"],
                             candidate_scan.PAGE_ROWS * candidate_scan.MAX_SCAN_PAGES)
        count = self.c.execute("""SELECT count(*) FROM bob_diagnostic_history
            WHERE id LIKE 'arch-%%' AND payload ? %s""", (cold.TAG,)).fetchone()[0]
        self.assertEqual(count, 900)
        self.assertIn(cold.TAG, self.c.execute(
            "SELECT payload FROM bob_diagnostic_history WHERE id='old'").fetchone()[0])


    def test_bounded_no_eligible_cursor_continues_then_wraps(self):
        self.c.execute("DELETE FROM bob_diagnostic_history WHERE id='old'")
        pointer = json.dumps({cold.TAG: ["f" * 32, 0], "timeframe": "15m"})
        rows = [
            ("arch-" + str(i), "analysis", 123.0, None, pointer, i)
            for i in range(2500)
        ]
        with self.c.cursor() as cur:
            cur.executemany("""INSERT INTO bob_diagnostic_history
            (id,stage,observed_at,build,payload,recorded_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,
                    now()-interval '12 hours'+(%s*interval '1 second'))""", rows)
        first = cold.offload_batch(self.c, self.drive)
        self.assertEqual(first["status"], "no-eligible-rows")
        self.assertEqual(first["scannedRows"],
                         candidate_scan.PAGE_ROWS * candidate_scan.MAX_SCAN_PAGES)
        self.assertIsNotNone(candidate_scan.cursor())
        second = cold.offload_batch(self.c, self.drive)
        self.assertEqual(second["status"], "no-eligible-rows")
        self.assertEqual(second["scannedRows"], 452)
        self.assertIsNone(candidate_scan.cursor())
        self.assertEqual(self.drive.files, {})
        count = self.c.execute("""SELECT count(*) FROM bob_diagnostic_history
            WHERE id LIKE 'arch-%%' AND payload ? %s""", (cold.TAG,)).fetchone()[0]
        self.assertEqual(count, 2500)

    def test_query_failure_never_advances_cursor_or_uploads(self):
        class QueryCanceled(Exception):
            pass
        class BrokenConn:
            autocommit = True
            def execute(self, sql, args=None):
                raise QueryCanceled("private-dsn-not-to-be-logged")
        self.assertIsNone(candidate_scan.cursor())
        with self.assertRaises(QueryCanceled):
            cold.offload_batch(BrokenConn(), self.drive)
        self.assertIsNone(candidate_scan.cursor())
        self.assertFalse(self.drive.files)
        self.assertEqual(
            self.c.execute("SELECT payload FROM bob_diagnostic_history WHERE id='old'").fetchone()[0],
            self.payload)
