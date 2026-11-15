"""A failed report must identify its stage without hiding or leaking the failure."""
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, Mock, patch
import psycopg
import decision_audit as audit


class ReportPhaseTests(unittest.TestCase):
    def test_each_subreport_failure_is_attributed_and_never_cached(self):
        stages = (
            ('rule_learning', 'rule-learning'),
            ('metric_quality', 'metric-quality'),
            ('product_precision', 'product-precision'),
            ('precision_learning', 'precision-learning'),
            ('ranking_learning', 'ranking-learning'),
            ('intraday_comparison', 'four-day-comparison'),
        )
        for module, phase in stages:
            with self.subTest(phase=phase), ExitStack() as stack:
                conn = MagicMock()
                stack.enter_context(patch.object(audit, '_report_cache', None))
                stack.enter_context(patch.object(audit, '_report_at', 42))
                stack.enter_context(patch.object(audit, '_load_report_rows', return_value=[]))
                stack.enter_context(patch.object(audit, '_load_prospective_rows', return_value=[]))
                for name, _ in stages:
                    stack.enter_context(patch.object(getattr(audit, name), 'report', return_value={}))
                error = psycopg.errors.QueryCanceled('private SQL token=secret account row')
                getattr(audit, module).report.side_effect = error
                logs = stack.enter_context(patch('builtins.print'))
                with self.assertRaises(psycopg.errors.QueryCanceled) as raised:
                    audit.report(conn)
                self.assertIs(raised.exception, error)
                self.assertIsNone(audit._report_cache)
                self.assertEqual(audit._report_at, 42)
                lines = [c.args[0] for c in logs.call_args_list]
                failures = [line for line in lines if 'report_read_canceled' in line]
                self.assertEqual(failures, ['BOB_AUDIT report_read_canceled phase=' + phase + ' error=QueryCanceled'])
                self.assertNotIn('secret', str(lines))
                self.assertNotIn('account row', str(lines))

    def test_reduced_window_failure_retains_both_attempts_and_original_error(self):
        error = psycopg.errors.QueryCanceled('secret')
        with patch.object(audit, '_load_report_rows', side_effect=error) as load, patch('builtins.print') as logs:
            with self.assertRaises(psycopg.errors.QueryCanceled) as raised:
                audit._build_report(MagicMock())
        self.assertIs(raised.exception, error)
        self.assertEqual(load.call_count, 2)
        self.assertEqual(load.call_args_list[1].args[1], audit.REPORT_BUSY_LIMIT)
        lines = [c.args[0] for c in logs.call_args_list]
        self.assertTrue(any('phase=decision-window ' in s for s in lines))
        self.assertTrue(any('phase=reduced-decision-window ' in s for s in lines))
        self.assertNotIn('secret', str(lines))

    def test_success_is_silent_and_unknown_phase_is_redacted(self):
        result = object()
        read = Mock(return_value=result)
        with patch('builtins.print') as logs:
            self.assertIs(audit._report_read_phase('metric-quality', read, 'arg'), result)
        logs.assert_not_called()
        read.assert_called_once_with('arg')
        with patch('builtins.print') as logs:
            with self.assertRaises(psycopg.errors.QueryCanceled):
                audit._report_read_phase('private\nsecret', Mock(side_effect=psycopg.errors.QueryCanceled('secret')))
        self.assertEqual(logs.call_args.args[0], 'BOB_AUDIT report_read_canceled phase=unknown error=QueryCanceled')

    def test_unrelated_error_is_not_mislabeled_as_cancellation(self):
        with patch('builtins.print') as logs:
            with self.assertRaises(ValueError):
                audit._report_read_phase('metric-quality', Mock(side_effect=ValueError('invalid')))
        logs.assert_not_called()
