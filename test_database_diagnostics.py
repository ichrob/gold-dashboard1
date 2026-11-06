import json
import os
import time
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock
import database_diagnostics as d
import storage_brief


class DiagnosticTests(unittest.TestCase):
    def test_write_transaction_is_refused_before_metadata_reads(self):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = ('off',)
        self.assertEqual(d.report(conn)['status'], 'read-only-required')
        self.assertEqual(conn.execute.call_count, 1)

    def test_error_is_redacted_and_never_marked_observed(self):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError('private-password-query-content')
        result = d.report(conn)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['observedAt'])
        self.assertNotIn('private-password', json.dumps(result))

    def test_fixed_projection_survives_storage_focus_without_secrets(self):
        raw = {'status': 'observed', 'observedAt': 123.0,
               'tables': [{'table': 'bob_candle_evidence', 'estimatedLiveRows': 25,
                           'privateRow': 'secret'}, {'table': 'private_credentials'}],
               'activity': {'sessions': 4, 'query': 'secret'},
               'capCountPlan': [{'node': 'Seq Scan', 'estimatedRows': 100,
                                 'Filter': 'secret', 'Relation Name': 'secret'}]}
        view = storage_brief.project({'databaseDiagnostics': raw})['databaseDiagnostics']
        self.assertEqual(len(view['tables']), 1)
        self.assertEqual(view['activity']['sessions'], 4)
        self.assertEqual(view['capCountPlan'][0]['node'], 'Seq Scan')
        self.assertNotIn('secret', json.dumps(view))
        self.assertNotIn('private_credentials', json.dumps(view))
        self.assertEqual(d.project({'tables': 3, 'capCountPlan': 'bad'})['tables'], [])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_readonly_probe_preserves_data_timeout_and_outer_transaction(self):
        import psycopg
        schema = 'db_diagnostics_' + str(time.time_ns())
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE SCHEMA ' + schema)
            conn.execute('SET search_path TO ' + schema)
            conn.execute('CREATE TABLE bob_diagnostic_history (id integer PRIMARY KEY)')
            conn.execute('INSERT INTO bob_diagnostic_history VALUES (1)')
            conn.commit()
            try:
                conn.execute('SET TRANSACTION READ ONLY')
                conn.execute("SET LOCAL statement_timeout='3s'")
                result = d.report(conn)
                self.assertEqual(result['status'], 'observed')
                self.assertTrue(result['capCountPlan'])
                self.assertEqual(result['tables'][0]['table'], 'bob_diagnostic_history')
                self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0], '3s')
                self.assertEqual(conn.execute('SHOW transaction_read_only').fetchone()[0], 'on')
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_diagnostic_history').fetchone()[0], 1)
                conn.rollback()
                # Missing relation makes EXPLAIN fail. The savepoint must
                # restore the timeout and leave the caller usable.
                conn.execute('DROP TABLE bob_diagnostic_history')
                conn.commit()
                conn.execute('SET TRANSACTION READ ONLY')
                conn.execute("SET LOCAL statement_timeout='3s'")
                self.assertEqual(d.report(conn)['status'], 'unavailable')
                self.assertEqual(conn.execute('SHOW statement_timeout').fetchone()[0], '3s')
                self.assertEqual(conn.execute('SELECT 1').fetchone()[0], 1)
                conn.rollback()
            finally:
                conn.rollback()
                conn.execute('DROP SCHEMA ' + schema + ' CASCADE')
                conn.commit()
