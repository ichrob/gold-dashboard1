"""Database lifecycle and concurrent archive access regressions."""
import os
import unittest
from unittest.mock import patch

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout
import bob_validation_store
import comparison_store
import push_server
import decision_audit


class PoolFailureTests(unittest.TestCase):
    def test_connection_exhaustion_is_retryable_at_startup(self):
        with patch.object(push_server, '_init_db_once', side_effect=[PoolTimeout(), None]) as init, patch.object(push_server.time, 'sleep'):
            push_server.init_db()
        self.assertEqual(init.call_count, 2)

    def test_market_spot_write_retries_transient_lock(self):
        from unittest.mock import MagicMock
        first, second = MagicMock(), MagicMock()
        first_conn, second_conn = MagicMock(), MagicMock()
        first.__enter__.return_value = first_conn
        second.__enter__.return_value = second_conn
        expected = {'ok': True}
        with patch.object(push_server, 'db', side_effect=[first, second]), \
                patch.object(push_server.bob_market_store, 'handle',
                             side_effect=[psycopg.errors.LockNotAvailable(), expected]) as handle, \
                patch.object(push_server.time, 'sleep') as sleep:
            result = push_server.write_market_spots({'spots': []})
        self.assertEqual(result, expected)
        self.assertEqual(handle.call_count, 2)
        handle.assert_any_call(first_conn, 'write', {'spots': []})
        handle.assert_any_call(second_conn, 'write', {'spots': []})
        sleep.assert_called_once_with(0.25)

    def test_secondary_timeout_preserves_report_and_discloses_missing_result(self):
        from unittest.mock import MagicMock, Mock
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (10,)
        with patch.object(decision_audit, '_load_report_rows', return_value=[]), patch.object(decision_audit, '_load_prospective_rows', side_effect=psycopg.errors.QueryCanceled()), patch.object(decision_audit.rule_learning, 'report', return_value={}), patch.object(decision_audit.intraday_comparison, 'report', return_value={}):
            result = decision_audit._build_report(conn)
        self.assertFalse(result['prospectiveReview']['available'])
        self.assertTrue(result['prospectiveReview']['retryable'])
        self.assertNotIn('phases', result['prospectiveReview'])
        self.assertIn('vorübergehend nicht verfügbar', result['scope'])
        self.assertEqual(result['total'], 10)

    def test_list_correction_read_does_not_take_writer_lock(self):
        from unittest.mock import MagicMock
        import list_corrections
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=({'products':[]},)
        list_corrections.handle(conn,{'action':'read'})
        self.assertNotIn('FOR UPDATE',conn.execute.call_args.args[0])
        conn.reset_mock()
        conn.execute.return_value.fetchone.return_value=({'products':[]},)
        with self.assertRaises(ValueError):
            list_corrections.handle(conn,{'action':'save'})
        self.assertIn('FOR UPDATE',conn.execute.call_args.args[0])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class DatabaseContentionTests(unittest.TestCase):
    def test_hourly_sampling_matches_original_query(self):
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_decision_audit (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)')
            conn.execute('CREATE TEMP TABLE bob_decision_outcomes (decision_id TEXT, horizon INTEGER, truth JSONB)')
            for n in range(20):
                payload = dict(reviewVariants=dict(version='signal-review-v1'), origin='background' if n % 3 else 'browser', ruleVersion=decision_audit.RULE_VERSION, direction='LONG' if n % 4 else 'NEUTRAL', fixture=n)
                conn.execute("INSERT INTO bob_decision_audit VALUES (%s,'2026-10-14 00:00Z'::timestamptz + %s * interval '20 minutes',%s)", (str(n), n, Jsonb(payload)))
                if n % 2:
                    conn.execute('INSERT INTO bob_decision_outcomes VALUES (%s,60,%s)', (str(n), Jsonb(dict(price=n))))
            expected = conn.execute("""SELECT a.payload,o.truth FROM (
                SELECT DISTINCT ON (date_trunc('hour',recorded_at)) id,payload,recorded_at
                FROM bob_decision_audit WHERE payload->'reviewVariants'->>'version'='signal-review-v1'
                AND payload->>'origin'='background' AND payload->>'ruleVersion'=%s
                AND payload->>'direction' IN ('LONG','SHORT')
                ORDER BY date_trunc('hour',recorded_at),recorded_at,id
                ) a LEFT JOIN bob_decision_outcomes o ON o.decision_id=a.id AND o.horizon=60
                ORDER BY a.recorded_at""", (decision_audit.RULE_VERSION,)).fetchall()
            self.assertEqual(decision_audit._load_prospective_rows(conn), expected)
            self.assertGreater(len(expected), 1)

    def test_pool_reuses_connections_and_rolls_back_failed_writes(self):
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        with ConnectionPool(dsn, min_size=1, max_size=1, timeout=1) as pool:
            with pool.connection() as conn:
                pid = conn.info.backend_pid
                conn.execute('CREATE TEMP TABLE pool_rollback_test (value INTEGER)')
            with self.assertRaises(ValueError):
                with pool.connection() as conn:
                    conn.execute('INSERT INTO pool_rollback_test VALUES (1)')
                    raise ValueError('abort')
            with pool.connection() as conn:
                self.assertEqual(conn.info.backend_pid, pid)
                self.assertEqual(conn.execute('SELECT count(*) FROM pool_rollback_test').fetchone()[0], 0)
                with self.assertRaises(PoolTimeout):
                    with pool.connection(timeout=0.05):
                        self.fail('Must not exceed the configured connection cap')
            with pool.connection() as conn:
                conn.execute('INSERT INTO pool_rollback_test VALUES (2)')
            with pool.connection() as conn:
                self.assertEqual(conn.execute('SELECT value FROM pool_rollback_test').fetchone(), (2,))

    def test_archive_readers_do_not_wait_for_writer_but_writers_stay_serialized(self):
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn) as setup:
            bob_validation_store.init(setup)
        for store, key in ((bob_validation_store, 68431026), (comparison_store, 68431027)):
            with self.subTest(store=store.__name__), psycopg.connect(dsn) as writer, psycopg.connect(dsn) as reader:
                writer.execute('SELECT pg_advisory_xact_lock(%s)', (key,))
                reader.execute("SET lock_timeout='100ms'")
                result = store.handle(reader, 'read', {})
                self.assertTrue(result['ok'])
                reader.commit()
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    store.handle(reader, 'write', {'events': []})
                reader.rollback()
                writer.commit()
                self.assertTrue(store.handle(reader, 'write', {'events': []})['ok'])


if __name__ == '__main__':
    unittest.main()
