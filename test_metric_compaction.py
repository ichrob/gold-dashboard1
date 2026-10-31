import os
import unittest
import uuid
from unittest.mock import MagicMock, patch
import metric_compaction as compact


class CompactionCoordinationTests(unittest.TestCase):
    def test_explicit_compactor_runs_after_backup_check_and_before_cold_observations(self):
        self.assertGreater(compact.COMPACTION_START_DELAY_SECONDS, 60)
        self.assertLess(compact.COMPACTION_START_DELAY_SECONDS, 90)

    def test_lock_conflict_identifies_fixed_category_without_consuming_attempt(self):
        config = {'id': 'one', 'observedAt': 4000, 'freeBytes': 200_000_000,
                  'databaseBytes': 600_000_000}
        for blocked_index, (expected, _) in enumerate(compact.LOCKS):
            with self.subTest(expected=expected):
                conn = MagicMock()
                conn.autocommit = True
                conn.__enter__.return_value = conn
                conn.execute.return_value.fetchone.side_effect = [(True,)] * blocked_index + [(False,)]
                with patch('archive_worker.status', return_value={'status': 'idle'}):
                    result = compact.run_once(config, factory=lambda: conn, now=4000)
                self.assertEqual(result, {'status': 'busy', 'blockedBy': expected})
                calls = [args[0][0] for args in conn.execute.call_args_list]
                self.assertEqual(len(calls), blocked_index + 1)
                self.assertTrue(all(sql.startswith('SELECT pg_try_advisory_lock') for sql in calls))
                self.assertNotIn('databaseBytes', result)
                self.assertNotIn('freeBytes', result)


class GuardTests(unittest.TestCase):
    def test_resume_requires_both_successful_indexes_and_full_timeout(self):
        proof={'status':'deferred','errorType':'QueryCanceled',
               'operations':[{'index':i,'status':'completed'} for i in compact.INDEXES]}
        self.assertTrue(compact.resumable(proof))
        for change in ({'status':'completed'}, {'errorType':'DiskFull'}, {'operations':[]},
                       {'operations':[{'index':compact.INDEXES[0],'status':'completed'}]}):
            self.assertFalse(compact.resumable({**proof,**change}))

    def test_missing_expired_and_future_observation_never_connect(self):
        def forbidden():
            raise AssertionError('must not connect')
        for config in ({}, {'id':'x','observedAt':1}, {'id':'x','observedAt':9000}):
            self.assertNotEqual(compact.run_once(config, forbidden, now=4000)['status'], 'completed')

    def test_budget_not_derived_from_database_size(self):
        def forbidden():
            raise AssertionError('must not connect')
        for budget in (0, 300_000_000, -1, True):
            result=compact.run_once({'id':'x','observedAt':4000,'freeBytes':budget,'databaseBytes':660_000_000}, forbidden, now=4000)
            self.assertEqual(result['status'],'invalid-budget')


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_compaction_preserves_values_keys_and_indexes(self):
        import psycopg
        schema='compact_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'], autocommit=True,
                options='-c statement_timeout=30000 -c lock_timeout=1000') as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                __import__('metric_quality').init(conn)
                conn.execute("INSERT INTO bob_metric_checks SELECT 'v',i::text,i,i,jsonb_build_object('payload',repeat(md5(i::text),40)) FROM generate_series(1,4000) i")
                conn.execute('DELETE FROM bob_metric_checks WHERE bar_at%10<>0')
                before=conn.execute('SELECT * FROM bob_metric_checks ORDER BY bar_at').fetchall()
                class Isolated:
                    def execute(self, sql, params=None):
                        sql=sql.replace('public.bob_metric',schema+'.bob_metric')
                        if params:
                            params=tuple(p.replace('public.bob_metric',schema+'.bob_metric') if isinstance(p,str) else p for p in params)
                        return conn.execute(sql,params)
                result=compact.compact(Isolated(),200_000_000)
                self.assertEqual(result['status'],'completed')
                self.assertGreater(result['observedRelationBytesDecrease'],0)
                self.assertEqual(conn.execute('SELECT * FROM bob_metric_checks ORDER BY bar_at').fetchall(),before)
                self.assertTrue(conn.execute("SELECT bool_and(indisvalid) FROM pg_index WHERE indrelid='bob_metric_checks'::regclass").fetchone()[0])
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    conn.execute("INSERT INTO bob_metric_checks SELECT * FROM bob_metric_checks LIMIT 1")
                self.assertIsNone(result['diskBytesFreed'])
                resumed=compact.compact(Isolated(),200_000_000,resume=True)
                self.assertEqual(resumed['status'],'completed')
                self.assertEqual(resumed['operations'],[])
                self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0],'90s')
                self.assertEqual(conn.execute('SELECT * FROM bob_metric_checks ORDER BY bar_at').fetchall(),before)
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_single_attempt_and_backup_guard(self):
        import psycopg
        schema='attempt_'+uuid.uuid4().hex
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn,autocommit=True) as admin:
            admin.execute('CREATE SCHEMA '+schema)
            admin.execute('CREATE TABLE '+schema+'.bob_archive_attempts(status text,updated_at timestamptz,receipt jsonb)')
            def factory():
                c=psycopg.connect(dsn,autocommit=True)
                c.execute('SET search_path TO '+schema)
                return c
            config={'id':'one','observedAt':4000,'freeBytes':200_000_000,'databaseBytes':1_000_000_000}
            try:
                with patch('archive_worker.status',return_value={'status':'idle'}), patch.object(compact,'compact',return_value={'status':'completed'}) as operation:
                    self.assertEqual(compact.run_once(config,factory,now=4000)['status'],'verified-backup-required')
                    operation.assert_not_called()
                    admin.execute('INSERT INTO '+schema+''' .bob_archive_attempts VALUES('verified',now(),'{"receipt":{"restoreVerified":true,"remoteDownloadVerified":true}}')''')
                    self.assertEqual(compact.run_once(config,factory,now=4000)['status'],'completed')
                    self.assertEqual(compact.run_once(config,factory,now=4000)['status'],'already-attempted')
                    operation.assert_called_once()
            finally:
                admin.execute('DROP SCHEMA '+schema+' CASCADE')

class TargetGuardTests(unittest.TestCase):
    def test_arbitrary_table_is_rejected_before_connect(self):
        def forbidden():raise AssertionError('must not connect')
        config={'id':'x','observedAt':4000,'freeBytes':250000000,'databaseBytes':600000000}
        for target in ('public.bob_decision_audit','diagnostic;DROP TABLE x','unknown'):
            self.assertEqual(compact.run_once({**config,'target':target},forbidden,now=4000)['status'],'invalid-target')
    def test_resume_cannot_cross_target(self):
        proof={'status':'deferred','errorType':'QueryCanceled',
            'operations':[{'index':i,'status':'completed'} for i in compact.INDEXES]}
        self.assertFalse(compact.resumable(proof,'diagnostic'))

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class DiagnosticCompactionTests(unittest.TestCase):
    def test_diagnostic_rewrite_preserves_all_original_values_and_indexes(self):
        import psycopg
        schema='diag_compact_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                conn.execute('''CREATE TABLE bob_diagnostic_history(id text primary key,recorded_at timestamptz,
                    stage text,observed_at double precision,trace_id text,payload jsonb)''')
                for suffix,cols in [('_time','recorded_at'),('_stage','stage,recorded_at'),('_source_window','stage,observed_at'),('_trace','trace_id,recorded_at')]:
                    conn.execute('CREATE INDEX bob_diagnostic_history'+suffix+' ON bob_diagnostic_history('+cols+')')
                conn.execute("INSERT INTO bob_diagnostic_history SELECT i::text,now(),'analysis',i,'trace',jsonb_build_object('original',repeat(md5(i::text),60),'number',9007199254740993) FROM generate_series(1,4000) i")
                conn.execute("UPDATE bob_diagnostic_history SET payload=jsonb_build_object('reference',id) WHERE id::int%10<>0")
                before=conn.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall()
                class Isolated:
                    def execute(self,sql,params=None):
                        sql=sql.replace('public.bob_diagnostic',schema+'.bob_diagnostic')
                        params=tuple(p.replace('public.bob_diagnostic',schema+'.bob_diagnostic') if isinstance(p,str) else p for p in params) if params else params
                        return conn.execute(sql,params)
                result=compact.compact(Isolated(),250000000,target='diagnostic')
                self.assertEqual(result['status'],'completed')
                self.assertLess(result['observedBudgetBytes'],250000000)
                self.assertGreater(result['observedRelationBytesDecrease'],0)
                self.assertEqual(conn.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall(),before)
                self.assertTrue(conn.execute("SELECT bool_and(indisvalid) FROM pg_index WHERE indrelid='bob_diagnostic_history'::regclass").fetchone()[0])
                self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0],'90s')
                self.assertIsNone(result['diskBytesFreed'])
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    conn.execute('INSERT INTO bob_diagnostic_history SELECT * FROM bob_diagnostic_history LIMIT 1')
            finally:conn.execute('DROP SCHEMA '+schema+' CASCADE')
