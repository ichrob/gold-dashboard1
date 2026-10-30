import unittest
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
        self.assertEqual(len(commands), 2)
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
        self.assertEqual(len(result['tables']), 2)
        self.assertTrue(all(r['status'] == 'deferred' for r in result['tables']))
        self.assertNotIn('secret', str(result))
        self.assertTrue(conn.closed)

    def test_pooled_transaction_connection_rejected(self):
        conn = Connection()
        conn.autocommit = False
        with self.assertRaises(ValueError):
            maintenance.run_once(lambda: conn)
        self.assertEqual(conn.calls, [])
        self.assertTrue(conn.closed)


if __name__ == '__main__':
    unittest.main()
