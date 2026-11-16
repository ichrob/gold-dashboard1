"""Operational cases must survive duplicated, oversized study detail."""
import copy
import json
import unittest
import bob_diagnostics as diagnostics
from bob_operations import compact_snapshot


class OperationsBudgetTests(unittest.TestCase):
    def source(self):
        return {'areas': {'operationsSummary': {
            'version': 1, 'observedAt': '2026-11-15T11:00:00+00:00',
            'readOnly': True, 'realOrders': False, 'problemIndexFresh': False,
            'actionStatus': 'unknown', 'actions': [],
            'cases': [{'code': 'source-missing', 'state': 'blocked',
                       'issueNumbers': [1], 'repairVerified': False}],
            'connections': {'items': [{'id': 'push', 'state': 'unknown'}]},
            'testOverview': {'items': [{'id': 'study', 'completed': False}],
                'qualityCampaign': {'status': 'failed', 'checkedAt': 123,
                    'winnerConfirmed': False, 'details': 'x' * 20000},
                'evidenceChains': [{'detail': 'z' * 20000}]}}}}

    def test_cases_and_failure_survive_budget_without_mutating_original(self):
        source = self.source()
        snapshot = copy.deepcopy(source)
        report = diagnostics.bounded_report(source, 3500)
        area = report['areas']['operationsSummary']
        self.assertNotIn('operationsSummary', report['omittedAreas'])
        for key in ('cases', 'actions', 'actionStatus', 'connections',
                    'observedAt', 'readOnly', 'realOrders', 'problemIndexFresh'):
            self.assertEqual(area[key], snapshot['areas']['operationsSummary'][key])
        campaign = area['testOverview']['qualityCampaign']
        self.assertEqual(campaign['status'], 'failed')
        self.assertEqual(campaign['checkedAt'], 123)
        self.assertFalse(campaign['winnerConfirmed'])
        self.assertEqual(campaign['omissionReason'], 'omitted-response-size-limit')
        self.assertTrue(area['truncated'])
        self.assertNotIn('status', area['testOverview']['evidenceChains'])
        self.assertEqual(source, snapshot)
        self.assertLessEqual(len(json.dumps(report, ensure_ascii=False,
            separators=(',', ':')).encode()), 3500)

    def test_fitting_source_is_not_compacted(self):
        source = self.source()
        self.assertEqual(diagnostics.bounded_report(source, 100000), source)

    def test_tiny_budget_still_reports_whole_area_omission(self):
        source = self.source()
        source['areas']['operationsSummary']['cases'] *= 100
        result = diagnostics.bounded_report(source, 2500)
        self.assertIn('operationsSummary', result['omittedAreas'])
        self.assertEqual(result['areas']['operationsSummary']['reason'],
                         'omitted-response-size-limit')

    def test_unknown_or_absent_source_is_not_promoted(self):
        for source in (None, {}, {'status': 'unavailable'},
                       {'testOverview': {'items': []}}):
            self.assertEqual(compact_snapshot(source), source)


if __name__ == '__main__':
    unittest.main()
