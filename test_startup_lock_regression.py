"""Rolling-start regressions for the original #1001 lock statements."""
import os
import unittest
from unittest.mock import patch

import psycopg
from psycopg import sql

import diagnostic_history
import evidence_repair


class _Result:
    def __init__(self, one=None, rows=None):
        self.one = one
        self.rows = rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class _EstablishedSchema:
    """Small catalog fixture; any emitted DDL/DML remains visible in calls."""
    relations = {
        'bob_test_repair_control', 'bob_test_repairs',
        'bob_test_repairs_due', 'bob_diagnostic_history',
        'bob_diagnostic_history_time', 'bob_diagnostic_history_stage',
        'bob_diagnostic_history_source_window',
        'bob_diagnostic_history_trace',
    }

    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        compact = ' '.join(statement.split())
        self.calls.append((compact, params))
        if compact.startswith('SELECT to_regclass'):
            name = params[0] if params else compact.split("'")[1]
            return _Result((name if name in self.relations else None,))
        if compact.startswith('SELECT 1 FROM bob_test_repair_control'):
            return _Result((1,))
        if 'SELECT attname FROM pg_attribute' in compact:
            return _Result(rows=[('id',), ('last_at',), ('signal_cursor',)])
        return _Result()


class StartupCatalogTests(unittest.TestCase):
    def test_established_repair_schema_emits_no_startup_write_or_ddl(self):
        conn = _EstablishedSchema()
        with patch('model_gap_review.init'), patch('training_handoff.init'):
            evidence_repair.init(conn)
        statements = [statement for statement, _ in conn.calls]
        self.assertFalse(any(statement.startswith(
            ('CREATE ', 'ALTER ', 'INSERT ')) for statement in statements))

    def test_established_diagnostic_schema_emits_no_startup_ddl(self):
        conn = _EstablishedSchema()
        with patch('storage_budget.init'):
            diagnostic_history.init(conn)
        statements = [statement for statement, _ in conn.calls]
        self.assertFalse(any(statement.startswith(
            ('CREATE ', 'ALTER ')) for statement in statements))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'CI PostgreSQL integration')
class StartupLockRegressionTests(unittest.TestCase):
    def setUp(self):
        import uuid
        self.dsn = os.environ['BOB_TEST_DATABASE_URL']
        self.schema = 'startup_lock_' + uuid.uuid4().hex
        with psycopg.connect(self.dsn) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(
                sql.Identifier(self.schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(
                sql.Identifier(self.schema)))
            evidence_repair.init(conn)
            diagnostic_history.init(conn)
            conn.commit()

    def tearDown(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(
                sql.Identifier(self.schema)))
            conn.commit()

    def use_schema(self, conn):
        conn.execute(sql.SQL('SET search_path TO {}').format(
            sql.Identifier(self.schema)))

    def test_existing_repair_init_does_not_wait_for_active_control_update(self):
        """The observed singleton INSERT must not run on an existing schema."""
        with psycopg.connect(self.dsn) as worker, psycopg.connect(self.dsn) as startup:
            self.use_schema(worker)
            self.use_schema(startup)
            worker.execute(
                'UPDATE bob_test_repair_control SET last_at=1 WHERE id=1')
            startup.execute("SET LOCAL lock_timeout='100ms'")
            evidence_repair.init(startup)
            self.assertEqual(startup.execute(
                'SELECT count(*) FROM bob_test_repair_control').fetchone()[0], 1)
            startup.rollback()
            worker.rollback()

    def test_existing_diagnostic_init_does_not_block_live_insert(self):
        """No-op index DDL must not hold a SHARE lock during rolling startup."""
        with psycopg.connect(self.dsn) as startup, psycopg.connect(self.dsn) as worker:
            self.use_schema(startup)
            self.use_schema(worker)
            diagnostic_history.init(startup)
            worker.execute("SET LOCAL lock_timeout='100ms'")
            worker.execute('''INSERT INTO bob_diagnostic_history
                (id,trace_id,stage,observed_at,payload)
                VALUES('event','trace','input',1,'{}'::jsonb)''')
            self.assertEqual(worker.execute(
                'SELECT count(*) FROM bob_diagnostic_history').fetchone()[0], 1)
            worker.rollback()
            startup.rollback()


if __name__ == '__main__':
    unittest.main()
