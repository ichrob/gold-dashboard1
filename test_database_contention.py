"""Database lifecycle and concurrent archive access regressions."""
import os
import inspect
import unittest
from unittest.mock import patch

import psycopg
from psycopg_pool import ConnectionPool, PoolTimeout
import bob_validation_store
import comparison_store
import push_server
import decision_audit


class PoolFailureTests(unittest.TestCase):
    def test_prospective_query_temporarily_prefers_cursor_indexes(self):
        """The expensive archive read must not leave planner settings changed."""
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [('decision-id', {'direction':'row'}, None)]
        with patch.object(decision_audit, '_prospective_query',
                          return_value=('SELECT id,payload,truth FROM fixture', ('rule',))):
            self.assertEqual(decision_audit._load_prospective_rows(conn),
                             [({'direction':'row'}, None)])
        calls = conn.execute.call_args_list
        self.assertEqual(calls[0].args, ('SET LOCAL enable_seqscan=off',))
        self.assertEqual(calls[1].args,
                         ('SELECT id,payload,truth FROM fixture', ('rule',)))
        self.assertEqual(calls[2].args, ('SET LOCAL enable_seqscan=on',))

    def test_service_init_never_builds_prospective_index(self):
        """Large archive indexes must be provisioned outside live startup."""
        source = inspect.getsource(decision_audit.init)
        self.assertNotIn(decision_audit.PROSPECTIVE_INDEX, source)
        self.assertNotIn('CREATE INDEX CONCURRENTLY', source)

    def test_connection_exhaustion_is_retryable_at_startup(self):
        with patch.object(push_server, '_init_db_once', side_effect=[PoolTimeout(), None]) as init, patch.object(push_server.time, 'sleep'):
            push_server.init_db()
        self.assertEqual(init.call_count, 2)

    def test_auth_session_retries_temporary_pool_exhaustion(self):
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.__enter__.return_value = MagicMock()
        expected = {'ok': True}
        with patch.object(push_server, 'db',
                          side_effect=[push_server.TooManyRequests(), connection]) as db, \
                patch.object(push_server.bob_session_store, 'handle',
                             return_value=expected) as handle, \
                patch.object(push_server.time, 'sleep') as sleep:
            result = push_server.handle_auth_session('check', {'sessionId': 'fixture'})
        self.assertEqual(result, expected)
        self.assertEqual(db.call_count, 2)
        handle.assert_called_once_with(connection.__enter__.return_value, 'check',
                                       {'sessionId': 'fixture'})
        sleep.assert_called_once_with(0.25)

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
                conn.execute("INSERT INTO bob_decision_audit VALUES (%s,date_trunc('hour',now()-interval '10 days') + %s * interval '20 minutes',%s)", (str(n), n, Jsonb(payload)))
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

    def test_sparse_hourly_sampling_preserves_oldest_eligible_and_retention(self):
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_decision_audit (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)')
            conn.execute('CREATE INDEX ON bob_decision_audit(recorded_at)')
            conn.execute('CREATE TEMP TABLE bob_decision_outcomes (decision_id TEXT, horizon INTEGER, truth JSONB)')
            valid = lambda name: Jsonb(dict(id=name, reviewVariants=dict(version='signal-review-v1'),
                                            origin='background', ruleVersion=decision_audit.RULE_VERSION,
                                            direction='LONG'))
            rows = [
                ('expired', "-interval '31 days' + interval '10 minutes'"),
                ('old-valid', "-interval '3 days' + interval '5 minutes'"),
                ('first', "-interval '12 hours' + interval '5 minutes'"),
                ('second', "-interval '12 hours' + interval '15 minutes'"),
                ('later', "-interval '10 hours' + interval '5 minutes'"),
            ]
            for name, offset in rows:
                conn.execute("INSERT INTO bob_decision_audit VALUES (%s,date_trunc('hour',now())" +
                             offset + ",%s)",(name,valid(name)))
            # Only the later event has outcome evidence; selection must never
            # cherry-pick it instead of the first independent observation.
            conn.execute("INSERT INTO bob_decision_outcomes VALUES ('second',60,%s)",
                         (Jsonb({'gain':3}),))
            full = decision_audit._load_prospective_rows(conn)
            self.assertEqual([row[0]['id'] for row in full],['old-valid','first','later'])
            self.assertIsNone(full[1][1])
            last_day = decision_audit._load_prospective_rows(conn,recent=True)
            self.assertEqual([row[0]['id'] for row in last_day],['first','later'])

    def test_prospective_sampling_uses_filtered_cursor_index(self):
        """The 30-day research scan must not re-filter the full JSONB archive."""
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_decision_audit (id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)')
            conn.execute('CREATE TEMP TABLE bob_decision_outcomes (decision_id TEXT, horizon INTEGER, truth JSONB)')
            conn.execute("""CREATE INDEX bob_audit_prospective_cursor
                ON bob_decision_audit ((payload->>'ruleVersion'),recorded_at,id)
                WHERE """ + decision_audit.PROSPECTIVE_INDEX_PREDICATE)
            valid = Jsonb(dict(reviewVariants=dict(version='signal-review-v1'),
                               origin='background', ruleVersion=decision_audit.RULE_VERSION,
                               direction='LONG'))
            irrelevant = Jsonb(dict(reviewVariants=dict(version='signal-review-v1'),
                                    origin='browser', ruleVersion=decision_audit.RULE_VERSION,
                                    direction='LONG'))
            for n in range(200):
                conn.execute("""INSERT INTO bob_decision_audit
                    VALUES (%s,now()-interval '2 days' + %s * interval '5 minutes',%s)""",
                             ('irrelevant-' + str(n), n, irrelevant))
            conn.execute("INSERT INTO bob_decision_audit VALUES ('eligible',now()-interval '1 hour',%s)",
                         (valid,))
            # Force a deterministic planner contract even though this fixture
            # is intentionally much smaller than the production archive.
            conn.execute('SET LOCAL enable_seqscan=off')
            self.assertEqual(len(decision_audit._load_prospective_rows(conn)), 1)
            sql, params = decision_audit._prospective_query()
            plan = conn.execute('EXPLAIN (FORMAT JSON) ' + sql, params).fetchone()[0]
            self.assertIn('bob_audit_prospective_cursor', str(plan))

    def test_future_dated_records_never_enter_historical_hourly_research(self):
        """Bad future rows cannot become historical evidence or widen the scan."""
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute("""CREATE TEMP TABLE bob_decision_audit (
                id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, payload JSONB)""")
            conn.execute('CREATE INDEX ON bob_decision_audit(recorded_at)')
            conn.execute("""CREATE TEMP TABLE bob_decision_outcomes (
                decision_id TEXT, horizon INTEGER, truth JSONB)""")
            def payload(name):
                return Jsonb(dict(id=name, reviewVariants=dict(version='signal-review-v1'),
                                  origin='background', ruleVersion=decision_audit.RULE_VERSION,
                                  direction='LONG'))
            # A malformed future timestamp must never appear in a 24h or
            # 30-day report, even though its direction/rule are otherwise valid.
            conn.execute("""INSERT INTO bob_decision_audit
                VALUES ('future-only', now()+interval '4 days', %s)""",
                         (payload('future-only'),))
            self.assertEqual(decision_audit._load_prospective_rows(conn), [])
            self.assertEqual(decision_audit._load_prospective_rows(conn,recent=True), [])
            # Preserve first eligible observation in every actual hour, not
            # the most favorable outcome. Later/future outcome is not a fill.
            for name, offset in [
                    ('first', "-interval '10 hours'"),
                    ('second', "-interval '10 hours' + interval '5 minutes'"),
                    ('past', "-interval '2 hours'")]:
                conn.execute("""INSERT INTO bob_decision_audit
                    VALUES (%s,date_trunc('hour', now()) + """ +
                    offset + """,%s)""", (name,payload(name)))
            conn.execute("""INSERT INTO bob_decision_outcomes
                VALUES ('second',60,%s)""", (Jsonb({'gain': 100}),))
            expected=['first','past']
            for recent in (False, True):
                rows=decision_audit._load_prospective_rows(conn,recent=recent)
                self.assertEqual([r[0]['id'] for r in rows], expected)
                self.assertIsNone(rows[0][1])
                self.assertNotIn('future-only', [r[0]['id'] for r in rows])

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
