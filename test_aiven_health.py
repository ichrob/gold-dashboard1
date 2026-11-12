import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import aiven_health as health
from test_aiven_readonly_probe import URI


class Connection:
    def __init__(self, busy=False):
        self.calls = []
        self.busy = busy
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute(self, sql):
        self.calls.append(sql)
        return self

    def fetchone(self):
        sql = self.calls[-1]
        if 'pg_try_advisory_lock' in sql:
            return (not self.busy,)
        if 'pg_postmaster_start_time' in sql:
            return (datetime(2026, 11, 12, tzinfo=timezone.utc), 9475775, 20, 'on')
        if 'pg_stat_activity' in sql:
            return (13, 1, 0, 0, 0)
        return (0, 0, 0, None)


class HealthTests(unittest.TestCase):
    def inspect(self, conn=None, env=None):
        conn = conn or Connection()
        with patch('psycopg.connect', return_value=conn) as connect:
            result = health.inspect(env or {'BOB_ARCHIVE_RESTORE_DATABASE_URL': URI})
        return result, conn, connect

    def test_bounded_read_only_aggregates_and_no_host_ram_claim(self):
        result, conn, connect = self.inspect()
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['clientConnections'], 1)
        self.assertIsNone(result['hostMemoryAvailablePercent'])
        self.assertIsNone(result['processMemoryBytes'])
        self.assertTrue(conn.closed)
        self.assertEqual(connect.call_count, 1)
        self.assertIn('default_transaction_read_only=on', connect.call_args.kwargs['options'])
        self.assertEqual(len(conn.calls), 4)
        self.assertNotIn('SECRET', str(result))

    def test_busy_target_skips_all_diagnostics(self):
        result, conn, _ = self.inspect(Connection(busy=True))
        self.assertEqual(result['status'], 'restore-busy')
        self.assertEqual(len(conn.calls), 1)
        self.assertTrue(conn.closed)

    def test_wrong_target_and_weak_tls_never_connect(self):
        for env in ({}, {'BOB_ARCHIVE_RESTORE_DATABASE_URL': URI, 'DATABASE_URL': URI},
                    {'BOB_ARCHIVE_RESTORE_DATABASE_URL': URI+'&host=production'},
                    {'BOB_ARCHIVE_RESTORE_DATABASE_URL': URI.replace('require','disable')}):
            _, _, connect = self.inspect(env=env or {'DATABASE_URL': URI})
            connect.assert_not_called()

    def test_errors_do_not_leak_credentials(self):
        with patch('psycopg.connect', side_effect=RuntimeError(URI)):
            result = health.inspect({'BOB_ARCHIVE_RESTORE_DATABASE_URL': URI})
        self.assertEqual(result['status'], 'observation-failed')
        self.assertNotIn('SECRET', str(result))

    def test_counter_growth_and_restart_are_not_an_oom_diagnosis(self):
        original, _, _ = self.inspect()
        current = {**original, 'tempBytes': 50, 'deadlocks': 1,
                   'clientConnections': 15, 'longActiveClients': 1}
        self.assertEqual(health.assess(current, original),
                         ['connection-pressure', 'long-query', 'new-deadlock', 'temporary-disk-growth'])
        current['postgresStartedAt'] = 'different'
        self.assertEqual(health.assess(current, original),
                         ['connection-pressure', 'long-query', 'postgres-restarted'])
        current['postgresStartedAt'] = original['postgresStartedAt']
        current['statsResetAt'] = 'new epoch'
        self.assertEqual(health.assess(current, original), ['connection-pressure', 'long-query'])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'requires isolated PostgreSQL')
class TargetLockIntegration(unittest.TestCase):
    def test_lock_is_shared_with_restore_and_survives_rollback(self):
        import psycopg
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn) as first, psycopg.connect(dsn) as second:
            self.assertEqual(first.execute(health.TARGET_LOCK_SQL).fetchone(), (True,))
            first.rollback()
            self.assertEqual(second.execute(health.TARGET_LOCK_SQL).fetchone(), (False,))
            first.close()
            self.assertEqual(second.execute(health.TARGET_LOCK_SQL).fetchone(), (True,))
