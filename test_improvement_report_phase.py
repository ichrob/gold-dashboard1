"""Canceled improvement reads identify a fixed phase without leaking content."""
import unittest
from unittest.mock import MagicMock, Mock, patch

import psycopg

import improvement_tracker as tracker


class ImprovementReportPhaseTests(unittest.TestCase):
    def test_each_phase_rethrows_original_cancellation_with_redacted_log(self):
        for phase in tracker._REPORT_READ_PHASES:
            with self.subTest(phase=phase), patch('builtins.print') as logs:
                error = psycopg.errors.QueryCanceled(
                    'private SQL token=secret account row')
                read = Mock(side_effect=error)
                with self.assertRaises(psycopg.errors.QueryCanceled) as raised:
                    tracker._report_read_phase(phase, read, 'arg')
                self.assertIs(raised.exception, error)
                read.assert_called_once_with('arg')
                self.assertEqual(
                    logs.call_args.args[0],
                    'BOB_IMPROVEMENT report_read_canceled phase=' + phase
                    + ' error=QueryCanceled')
                self.assertNotIn('secret', str(logs.call_args_list))
                self.assertNotIn('account row', str(logs.call_args_list))

    def test_unknown_phase_is_redacted_and_unrelated_error_is_silent(self):
        with patch('builtins.print') as logs:
            with self.assertRaises(psycopg.errors.QueryCanceled):
                tracker._report_read_phase(
                    'private\nsecret',
                    Mock(side_effect=psycopg.errors.QueryCanceled('secret')))
        self.assertEqual(
            logs.call_args.args[0],
            'BOB_IMPROVEMENT report_read_canceled phase=unknown '
            'error=QueryCanceled')
        self.assertNotIn('secret', str(logs.call_args_list))

        with patch('builtins.print') as logs:
            with self.assertRaises(ValueError):
                tracker._report_read_phase(
                    'protocol', Mock(side_effect=ValueError('invalid')))
        logs.assert_not_called()

    def test_report_attributes_the_first_database_read(self):
        error = psycopg.errors.QueryCanceled('private row')
        conn = MagicMock()
        conn.execute.side_effect = error
        with patch('builtins.print') as logs:
            with self.assertRaises(psycopg.errors.QueryCanceled) as raised:
                tracker.report(conn, now=tracker.START)
        self.assertIs(raised.exception, error)
        self.assertEqual(
            logs.call_args.args[0],
            'BOB_IMPROVEMENT report_read_canceled phase=protocol '
            'error=QueryCanceled')
        self.assertNotIn('private row', str(logs.call_args_list))


if __name__ == '__main__':
    unittest.main()
