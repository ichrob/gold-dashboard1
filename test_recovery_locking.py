"""Regression: high-frequency authentication reads must never lock recovery rows.

The real PostgreSQL case reproduces a concurrent password-reset transaction.
Never cache successful credentials or relax session invalidation.
"""
import os
import secrets
import unittest
from unittest.mock import MagicMock

import bob_recovery


class RecoveryStateReadTests(unittest.TestCase):
    def test_new_account_read_is_read_only_with_original_defaults(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        result = bob_recovery.handle(conn, 'state', {'account': 'a' * 64})
        self.assertEqual(result, {'passwordHash': None, 'version': 0})
        self.assertEqual(conn.execute.call_count, 1)
        statement, parameters = conn.execute.call_args.args
        self.assertEqual(parameters, ('a' * 64,))
        self.assertTrue(statement.strip().upper().startswith('SELECT'))
        self.assertNotIn('FOR UPDATE', statement.upper())

    def test_existing_password_and_version_are_returned_without_writes(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = ('pbkdf2-test', 7)
        result = bob_recovery.handle(conn, 'state', {'account': 'b' * 64})
        self.assertEqual(result, {'passwordHash': 'pbkdf2-test', 'version': 7})
        self.assertEqual(conn.execute.call_count, 1)
        self.assertNotIn('FOR UPDATE', conn.execute.call_args.args[0].upper())

    def test_reset_actions_still_use_exclusive_row_lock(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (None, 0, None, 0, 0, 0, 0)
        result = bob_recovery.handle(conn, 'issue', {'account': 'c' * 64, 'tokenHash': 'd' * 64}, now=10000)
        self.assertTrue(result['issued'])
        statements = [args.args[0] for args in conn.execute.call_args_list]
        self.assertTrue(any('FOR UPDATE' in sql for sql in statements))


@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'), 'Requires CI PostgreSQL')
class RecoveryPostgresConcurrencyTests(unittest.TestCase):
    def test_read_during_row_lock_returns_committed_state(self):
        import psycopg
        dsn = os.environ['BOB_TEST_DATABASE_URL']
        account = secrets.token_hex(32)
        with psycopg.connect(dsn) as setup:
            bob_recovery.init(setup)
            setup.execute('INSERT INTO bob_recovery(account,password_hash,version) VALUES(%s,%s,%s)',
                          (account, 'old-hash', 3))
        with psycopg.connect(dsn) as writer:
            with writer.transaction():
                writer.execute('UPDATE bob_recovery SET version=4 WHERE account=%s', (account,))
                # Auth read must not wait on the uncommitted writer's lock.
                with psycopg.connect(dsn, options='-c lock_timeout=200 -c statement_timeout=1000') as reader:
                    state = bob_recovery.handle(reader, 'state', {'account': account})
                    self.assertEqual(state, {'passwordHash': 'old-hash', 'version': 3})
            with psycopg.connect(dsn) as reader:
                state = bob_recovery.handle(reader, 'state', {'account': account})
                self.assertEqual(state['version'], 4)


if __name__ == '__main__':
    unittest.main()
