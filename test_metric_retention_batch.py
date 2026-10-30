"""Keep metric-retention maintenance bounded without losing original evidence."""
import os
import unittest
import uuid

import metric_quality as metric


class Collector:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        if self.fail:
            raise RuntimeError("query unavailable")


class RetentionUnitTests(unittest.TestCase):
    def setUp(self):
        self.before = metric._PRUNE_NEXT_AT
        metric._PRUNE_NEXT_AT = 0.0

    def tearDown(self):
        metric._PRUNE_NEXT_AT = self.before

    def test_only_existing_metric_window_in_bounded_batch(self):
        conn = Collector()
        now = 1_800_000_000_000
        self.assertTrue(metric._prune_expired_checks(conn, now, lambda:1000.0))
        self.assertFalse(metric._prune_expired_checks(conn, now+1000, lambda:1100.0))
        self.assertEqual(len(conn.calls), 1)
        sql, params = conn.calls[0]
        self.assertIn("DELETE FROM bob_metric_checks", sql)
        self.assertIn("WHERE checked_at<%s", sql)
        self.assertIn("LIMIT %s FOR UPDATE SKIP LOCKED", sql)
        self.assertNotIn("bob_decision_audit", sql)
        self.assertNotIn("bob_diagnostic_history", sql)
        self.assertEqual(params, (now-30*86400000, 500))
        self.assertTrue(metric._prune_expired_checks(conn, now+301000, lambda:1301.0))
        self.assertEqual(len(conn.calls), 2)

    def test_lock_unavailable_skips_without_side_effects(self):
        conn = Collector()
        metric._PRUNE_LOCK.acquire()
        try:
            self.assertFalse(metric._prune_expired_checks(conn, 10000, lambda:1000.0))
            self.assertFalse(conn.calls)
        finally:
            metric._PRUNE_LOCK.release()

    def test_failure_does_not_advance_next_attempt(self):
        conn = Collector(fail=True)
        with self.assertRaises(RuntimeError):
            metric._prune_expired_checks(conn, 10000, lambda:1000.0)
        self.assertEqual(metric._PRUNE_NEXT_AT, 0.0)
        self.assertTrue(metric._prune_expired_checks(Collector(), 10000, lambda:1001.0))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'PostgreSQL integration in CI')
class RetentionPostgresTests(unittest.TestCase):
    def test_real_postgres_retains_fresh_checks_and_batches_old_checks(self):
        import psycopg
        from psycopg import sql
        schema = 'metric_retain_' + uuid.uuid4().hex
        now = 1_800_000_000_000
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                metric.init(conn)
                conn.execute('''INSERT INTO bob_metric_checks
                  SELECT 'test', 'scope', n, %s, '{}'::jsonb
                  FROM generate_series(1, 520) n''', (now-30*86400000-1,))
                conn.execute('''INSERT INTO bob_metric_checks
                  VALUES('test','scope',521,%s,'{}'::jsonb)''', (now-30*86400000,))
                metric._PRUNE_NEXT_AT = 0
                self.assertTrue(metric._prune_expired_checks(conn, now,lambda:1000.0))
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_metric_checks').fetchone()[0], 21)
                self.assertTrue(metric._prune_expired_checks(conn, now,lambda:1301.0))
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_metric_checks').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT bar_at FROM bob_metric_checks').fetchone()[0], 521)
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


if __name__ == '__main__':
    unittest.main()
