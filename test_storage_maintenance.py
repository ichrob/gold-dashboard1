import unittest
import os
import uuid
from unittest.mock import patch
import storage_maintenance as maintenance


class Connection:
    autocommit = True

    def __init__(self, locked=True, candidates=True, fail=False):
        self.locked, self.candidates, self.fail = locked, candidates, fail
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.startswith('VACUUM') and self.fail:
            raise RuntimeError('secret connection detail')
        return self

    def fetchone(self):
        if 'pg_try_advisory_lock' in self.calls[-1][0]:
            return (self.locked,)
        return (3000,) if self.candidates else None


class MaintenanceTests(unittest.TestCase):
    def test_busy_never_vacuums(self):
        conn = Connection(locked=False)
        self.assertEqual(maintenance.run_once(lambda: conn)['status'], 'busy')
        self.assertEqual(len(conn.calls), 1)
        self.assertTrue(conn.closed)

    def test_only_allowlisted_nonrewriting_commands(self):
        conn = Connection()
        result = maintenance.run_once(lambda: conn)
        commands = [sql for sql, _ in conn.calls if sql.startswith('VACUUM')]
        self.assertEqual(len(commands), 4)
        for sql, table in zip(commands, maintenance._TABLES):
            self.assertEqual(sql, 'VACUUM (SKIP_LOCKED, TRUNCATE FALSE, PARALLEL 0) ONLY public.' + table)
        self.assertIsNone(result['diskBytesFreed'])
        self.assertFalse(result['evidenceDeleted'])
        self.assertTrue(conn.closed)

    def test_no_candidates_no_vacuum(self):
        conn = Connection(candidates=False)
        self.assertEqual(maintenance.run_once(lambda: conn)['tables'], [])
        self.assertFalse(any(sql.startswith('VACUUM') for sql, _ in conn.calls))

    def test_errors_sanitized_and_connection_closed(self):
        conn = Connection(fail=True)
        result = maintenance.run_once(lambda: conn)
        self.assertEqual(len(result['tables']), 4)
        self.assertTrue(all(r['status'] == 'deferred' for r in result['tables']))
        self.assertNotIn('secret', str(result))
        self.assertTrue(conn.closed)

    def test_tail_reclamation_runs_after_recent_autovacuum(self):
        conn = Connection(candidates=False)
        base_fetch = conn.fetchone
        sizes = iter([81920, 16384])
        conn.fetchone = lambda: ((next(sizes),) if 'pg_total_relation_size' in conn.calls[-1][0] else base_fetch())
        result = maintenance.run_once(lambda: conn, reclaim_metric_tail=True)
        commands = [sql for sql, _ in conn.calls if sql.startswith('VACUUM')]
        self.assertEqual(commands, ['VACUUM (SKIP_LOCKED, TRUNCATE TRUE, PARALLEL 0) ONLY public.bob_metric_checks'])
        self.assertIn(("SET statement_timeout = '10s'", None), conn.calls)
        self.assertEqual(result['tables'][0]['observedRelationBytesDecrease'], 65536)
        self.assertIsNone(result['diskBytesFreed'])

    def test_tail_timeout_is_deferred_without_false_savings(self):
        conn = Connection(fail=True)
        result = maintenance.run_once(lambda: conn, reclaim_metric_tail=True)
        self.assertEqual(result['tables'][-1]['status'], 'deferred')
        self.assertNotIn('observedRelationBytesDecrease', result['tables'][-1])
        self.assertNotIn('secret', str(result))
        self.assertTrue(conn.closed)

    def test_new_tail_targets_are_bounded_and_explicit(self):
        for flag, table in [('reclaim_analysis_tail','bob_diagnostic_history'),
                            ('reclaim_observation_tail','bob_improvement_observations'),
                            ('reclaim_image_tail','bob_android_list_images')]:
            conn=Connection(candidates=False)
            base=conn.fetchone
            conn.fetchone=lambda: (1000,) if 'pg_total_relation_size' in conn.calls[-1][0] else base()
            result=maintenance.run_once(lambda:conn, **{flag:True})
            commands=[sql for sql,_ in conn.calls if sql.startswith('VACUUM')]
            self.assertEqual(commands,['VACUUM (SKIP_LOCKED, TRUNCATE TRUE, PARALLEL 0) ONLY public.'+table])
            self.assertEqual(result['tables'][0]['observedRelationBytesDecrease'],0)

    def test_pooled_transaction_connection_rejected(self):
        conn = Connection()
        conn.autocommit = False
        with self.assertRaises(ValueError):
            maintenance.run_once(lambda: conn)
        self.assertEqual(conn.calls, [])
        self.assertTrue(conn.closed)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class PostgreSQLMaintenanceTests(unittest.TestCase):
    def test_real_tail_reclamation_preserves_live_row_and_measures_shrink(self):
        import psycopg
        name = 'tail_test_' + uuid.uuid4().hex
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute('CREATE TABLE public.' + name + ' (id int, payload text)')
            try:
                admin.execute('INSERT INTO public.' + name + " SELECT i, repeat(md5(i::text), 40) FROM generate_series(1,2000) i")
                admin.execute('DELETE FROM public.' + name + ' WHERE id>1')
                before = admin.execute('SELECT * FROM public.' + name).fetchall()
                class TailConnection:
                    autocommit = True
                    def __enter__(self):
                        self.conn = psycopg.connect(dsn, autocommit=True,
                            options='-c lock_timeout=1000')
                        return self
                    def __exit__(self, *args):
                        self.conn.close()
                    def execute(self, statement, params=None):
                        # Exercise production SQL against an isolated test table.
                        mapped = tuple('public.' + name if p == 'public.bob_metric_checks' else p for p in params) if params else params
                        return self.conn.execute(statement.replace('public.bob_metric_checks', 'public.' + name), mapped)
                with patch.object(maintenance, '_TABLES', ('bob_metric_checks',)):
                    result = maintenance.run_once(TailConnection, reclaim_metric_tail=True)
                self.assertEqual(result['tables'][0]['status'], 'command-completed')
                self.assertGreater(result['tables'][0]['observedRelationBytesDecrease'], 0)
                self.assertEqual(admin.execute('SELECT * FROM public.' + name).fetchall(), before)
            finally:
                admin.execute('DROP TABLE public.' + name)

    def test_real_vacuum_preserves_live_json_and_releases_session_lock(self):
        import psycopg
        name = 'maintenance_test_' + uuid.uuid4().hex
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        payload = '{"original": [1, "unchanged", null]}'
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute('CREATE TABLE public.' + name + ' (id int primary key, payload jsonb)')
            try:
                admin.execute('INSERT INTO public.' + name + ' VALUES (1,%s::jsonb),(2,%s::jsonb)', (payload, payload))
                admin.execute('DELETE FROM public.' + name + ' WHERE id=2')
                before = admin.execute('SELECT * FROM public.' + name).fetchall()
                class CandidateConnection:
                    # Statistics updates are asynchronous. Force only candidate
                    # selection; run the actual lock and VACUUM against PG18.
                    autocommit = True
                    def __enter__(self):
                        self.conn = psycopg.connect(dsn, autocommit=True)
                        return self
                    def __exit__(self, *args):
                        self.conn.close()
                    def execute(self, statement, params=None):
                        if statement.startswith('SELECT n_dead_tup'):
                            class Row:
                                def fetchone(self):
                                    return (1,)
                            return Row()
                        return self.conn.execute(statement, params)
                with patch.object(maintenance, '_TABLES', (name,)):
                    result = maintenance.run_once(CandidateConnection)
                self.assertEqual(result['tables'], [{'table': name, 'status': 'command-completed'}])
                self.assertEqual(admin.execute('SELECT * FROM public.' + name).fetchall(), before)
                acquired = admin.execute("SELECT pg_try_advisory_lock(hashtext('bob_storage_maintenance_v1'))").fetchone()[0]
                self.assertTrue(acquired)
                admin.execute("SELECT pg_advisory_unlock(hashtext('bob_storage_maintenance_v1'))")
            finally:
                admin.execute('DROP TABLE public.' + name)


if __name__ == '__main__':
    unittest.main()
