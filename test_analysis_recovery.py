"""Bounded recovery of the observed Node SIGABRT, without stale-result reuse."""
import json
import signal
import subprocess
import unittest
from unittest.mock import patch
import background_push as b


class AnalysisRecoveryTests(unittest.TestCase):
    def result(self, code=0, output=None):
        return subprocess.CompletedProcess([], code, json.dumps(output or {'ready': False, 'priceFresh': False}), '')

    def test_abort_recovers_with_remaining_budget_and_current_evaluation(self):
        with patch.object(b.subprocess, 'run', side_effect=[self.result(-signal.SIGABRT), self.result()]) as run, patch.object(b.time, 'monotonic', side_effect=[100, 100, 102, 103]):
            result = b.analyze({'spots': {}}, {'timeframe': '15m'})
        self.assertFalse(result['ready'])
        self.assertFalse(result['priceFresh'])
        self.assertEqual(run.call_count, 2)
        self.assertEqual([c.kwargs['timeout'] for c in run.call_args_list], [10, 8])
        self.assertEqual(run.call_args_list[0].kwargs['input'], run.call_args_list[1].kwargs['input'])

    def test_repeated_abort_fails_closed(self):
        with patch.object(b.subprocess, 'run', return_value=self.result(-signal.SIGABRT)) as run:
            with self.assertRaises(RuntimeError): b.analyze({}, {})
        self.assertEqual(run.call_count, 2)

    def test_application_errors_and_timeouts_are_not_retried(self):
        with patch.object(b.subprocess, 'run', return_value=self.result(1)) as run:
            with self.assertRaises(RuntimeError): b.analyze({}, {})
        self.assertEqual(run.call_count, 1)
        with patch.object(b.subprocess, 'run', side_effect=subprocess.TimeoutExpired('node', 10)) as run:
            with self.assertRaises(subprocess.TimeoutExpired): b.analyze({}, {})
        self.assertEqual(run.call_count, 1)

    def test_exhausted_budget_does_not_start_another_process(self):
        with patch.object(b.subprocess, 'run', return_value=self.result(-signal.SIGABRT)) as run, patch.object(b.time, 'monotonic', side_effect=[100, 100, 111]):
            with self.assertRaises(TimeoutError): b.analyze({}, {})
        self.assertEqual(run.call_count, 1)

    def test_malformed_trade_is_validation_error(self):
        for trade in ([], 'active', 1, False):
            with self.subTest(trade=trade), self.assertRaises(ValueError):
                b.config({'trade': trade})
