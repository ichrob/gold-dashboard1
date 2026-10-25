"""Diagnosis #16: SQL-query timing is an observation, never a repaired timeout.

All tests avoid production database access, market calculations and orders.
"""
import json
import unittest
from unittest.mock import MagicMock, Mock, patch

import decision_audit as audit
import bob_diagnostics as diagnostics


class AuditProbeTests(unittest.TestCase):
    def test_no_query_after_restart_is_unknown_not_healthy(self):
        with patch.object(audit, '_PROSPECTIVE_QUERY_LAST', None):
            state = audit.prospective_query_probe()
        self.assertEqual(state['status'], 'not-observed')
        self.assertFalse(state['causeVerified'])
        self.assertTrue(state['readOnly'])
        self.assertFalse(state['realOrders'])
        self.assertNotIn('fullState', state)

    def test_timeout_with_day_fallback_is_partial_not_recovered_month(self):
        with patch.object(audit, '_PROSPECTIVE_QUERY_LAST', None):
            audit._remember_prospective_query('query-timeout', 5100,
                                              'completed-partial', 321)
            state = audit.prospective_query_probe()
        self.assertEqual(state['status'], 'observed')
        self.assertEqual(state['fullWindow'], '30-days')
        self.assertEqual(state['fallbackWindow'], '24-hours')
        self.assertFalse(state['fullWindowQueryCompleted'])
        self.assertFalse(state['causeVerified'])
        self.assertEqual(state['fullDurationMs'], 5100)
        self.assertEqual(state['fallbackDurationMs'], 321)
        self.assertNotIn('password', json.dumps(state))
        self.assertIn('not full-window', state['note'])

    def test_complete_and_both_timeout_paths_keep_distinct_categories(self):
        with patch.object(audit, '_PROSPECTIVE_QUERY_LAST', None):
            audit._remember_prospective_query('completed', 12, 'not-needed', None)
            complete = audit.prospective_query_probe()
            self.assertTrue(complete['fullWindowQueryCompleted'])
            self.assertIsNone(complete['fallbackDurationMs'])
            audit._remember_prospective_query('query-timeout', 2000,
                                              'query-timeout', 2100)
            failed = audit.prospective_query_probe()
        self.assertFalse(failed['fullWindowQueryCompleted'])
        self.assertEqual(failed['fallbackState'], 'query-timeout')
        self.assertFalse(failed['causeVerified'])

    def test_reject_forged_success_and_private_payloads(self):
        invalid = (
            ('database fixed', 100, 'not-needed', None),
            ('completed', -1, 'not-needed', None),
            ('completed', True, 'not-needed', None),
            ('completed', 10, 'completed-partial', 2),
            ('query-timeout', 10, 'not-needed', None),
            ('query-timeout', 10, 'completed-partial', None),
            ('query-timeout', 10, 'completed-partial', -1),
            ('query-timeout', 10, 'completed-partial', 'password=SECRET'),
        )
        with patch.object(audit, '_PROSPECTIVE_QUERY_LAST', None):
            for args in invalid:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    audit._remember_prospective_query(*args)
            self.assertEqual(audit.prospective_query_probe()['status'],
                             'not-observed')

    def test_private_push_report_reads_process_cache_without_new_sql(self):
        portfolios = Mock(POLICIES=[])
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = (0, 0)
        evaluator = Mock()
        evaluator.status.return_value = {'completed': 1, 'queueTimeouts': 0}
        paper = Mock()
        paper.snapshot.return_value = {'state':'paused'}
        with patch.object(audit, '_PROSPECTIVE_QUERY_LAST', None):
            audit._remember_prospective_query('query-timeout', 1000,
                                              'completed-partial', 13)
            result = diagnostics.push_snapshot(conn, evaluator, paper, portfolios)
        self.assertEqual(conn.execute.call_count, 1)
        self.assertEqual(result['databaseAudit']['fallbackState'],
                         'completed-partial')
        self.assertEqual(result['databaseAudit']['scope'],
                         'process-local-last-research-query-attempt')
        self.assertFalse(result['databaseAudit']['causeVerified'])
        self.assertFalse(result['databaseAudit']['realOrders'])
        self.assertFalse(result['push']['deliveryStatus'] == 'delivered')
        self.assertNotIn('SELECT', json.dumps(result['databaseAudit']))

    def test_build_report_stores_real_attempt_state_not_mock_fills(self):
        import psycopg
        conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=(0,)
        with patch.object(audit, '_PROSPECTIVE_QUERY_LAST', None), \
             patch.object(audit, '_load_report_rows', return_value=[]), \
             patch.object(audit, '_load_prospective_rows',
                          side_effect=[psycopg.errors.QueryCanceled('timeout'), []]), \
             patch.object(audit.rule_learning, 'report', return_value={}), \
             patch.object(audit.intraday_comparison, 'report', return_value={}), \
             patch.object(audit.ranking_learning, 'report', return_value={}), \
             patch.object(audit.precision_learning, 'report', return_value={}), \
             patch.object(audit.metric_quality, 'report', return_value={}), \
             patch.object(audit.product_precision, 'report', return_value={}):
            result = audit._build_report(conn)
            status = audit.prospective_query_probe()
        self.assertEqual(status['fullState'], 'query-timeout')
        self.assertEqual(status['fallbackState'], 'completed-partial')
        self.assertEqual(status['fullDurationMs'],
                         result['prospectiveReview']['queryTiming']['fullDurationMs'])
        self.assertFalse(status['fullWindowQueryCompleted'])
        self.assertFalse(result['prospectiveReview']['automaticRuleChange'])


if __name__=='__main__':
    unittest.main()
