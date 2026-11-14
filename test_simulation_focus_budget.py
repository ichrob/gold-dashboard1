"""Keep bounded simulation account evidence ahead of optional research history."""
import copy
import json
import unittest

import bob_diagnostics as diagnostics


class FocusedSimulationBudgetTests(unittest.TestCase):
    def test_optional_comparisons_do_not_evict_virtual_accounts(self):
        original = {
            'readOnly': True, 'realOrders': False,
            'areas': {
                'comparisonEvidence': {'status': 'observed', 'historical': 'H' * 14000},
                'riskPaper': {'status': 'observed', 'detail': 'R' * 9500},
                'newStudiesBrief': {'status': 'observed', 'details': 'N' * 7500},
                'simulationAndPush': {
                    'status': 'observed',
                    'paper': {'state': 'paused'},
                    'accounts': [
                        {'profile': 'paper-%02d' % i, 'status': 'running',
                         'cash': 1000.0, 'equity': 1010.0,
                         'costsDebitedEur': 3.2,
                         'lastTradingEntryBlockCode': 'no-confirmed-plan'}
                        for i in range(11)],
                    'push': {'activeMonitors': 1}
                },
                'paperProfitEvidence': {
                    'status': 'observed', 'strategyWinnerConfirmed': False,
                    'netProductReturnsVerified': False
                },
                'simulationRuntimeBrief': {
                    'status': 'observed', 'paper': {'accountsTotal': 11}
                },
                'entryBlockEvidence': {
                    'status': 'observed', 'accounts': [{'profile': 'paper-01',
                      'reasonCounts': [{'code': 'no-confirmed-plan', 'checks': 9}]}]
                }
            }
        }
        snapshot = copy.deepcopy(original)
        limited = diagnostics.bounded_report(original, 6800)
        areas = limited['areas']
        self.assertEqual(len(areas['simulationAndPush']['accounts']), 11)
        self.assertEqual(areas['simulationAndPush']['accounts'][0]['cash'], 1000.0)
        self.assertEqual(areas['simulationAndPush']['accounts'][0]['costsDebitedEur'], 3.2)
        self.assertFalse(areas['paperProfitEvidence']['strategyWinnerConfirmed'])
        self.assertEqual(areas['entryBlockEvidence']['accounts'][0]['reasonCounts'][0]['checks'], 9)
        self.assertIn('comparisonEvidence', limited['omittedAreas'])
        self.assertLessEqual(len(json.dumps(limited, ensure_ascii=False,
                                           separators=(',', ':')).encode('utf-8')), 6800)
        self.assertEqual(original, snapshot)

    def test_truly_tiny_budget_is_not_claimed_as_complete(self):
        original = {'areas': {'simulationAndPush': {
            'status': 'observed', 'accounts': [
                {'profile': str(i), 'cash': 100, 'equity': 100} for i in range(40)]}}}
        limited = diagnostics.bounded_report(original, 650)
        self.assertTrue(limited['truncated'])
        self.assertIn('simulationAndPush', limited['omittedAreas'])
        self.assertEqual(limited['areas']['simulationAndPush']['status'], 'unavailable')
        self.assertEqual(limited['areas']['simulationAndPush']['reason'],
                         'omitted-response-size-limit')


if __name__ == '__main__':
    unittest.main()
