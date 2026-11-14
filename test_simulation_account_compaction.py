"""Live-size virtual account snapshots must survive the response budget."""
import copy
import json
import unittest

import bob_diagnostics as diagnostics


class LargeAccountProjectionTests(unittest.TestCase):
    def test_keep_all_eleven_account_clocks_and_costs_under_realistic_cap(self):
        accounts = []
        for index in range(11):
            accounts.append({
                'profile': 'paper-%02d' % index,
                'status': 'running',
                'initialCapital': 800 if index == 0 else 1000,
                'cash': 800 if index == 0 else 1000,
                'equity': 800 if index == 0 else 1000,
                'costsDebitedEur': 0.0, 'checkedAt': 1794603599987,
                'lastTradingEntryBlockCode': 'source-not-fresh',
                'lastTradingEntryBlockAt': 1794603536000,
                'recentCases': {'status': 'observed', 'items': [
                    {'raw': 'x'*3000} for _ in range(5)]},
                'forwardEvidence': {'status': 'collecting',
                    'actualNetVerified': False, 'winnerConfirmed': False,
                    'calibration': {'raw': 'f'*1800},
                    'validation': {'raw': 'v'*1000}},
                'netEvidenceSample': {'status': 'observed',
                                      'brokerNetVerified': False,
                                      'raw': 'n'*1300},
                'extraDetails': {'raw': 'e'*1500},
            })
        source = {
            'readOnly': True, 'realOrders': False,
            'areas': {
                'simulationAndPush': {
                    'status': 'observed', 'readOnly': True,
                    'realOrders': False,
                    'accounts': accounts,
                    'paper': {'state': 'paused', 'accountsTotal': 11,
                              'raw': 'p'*12000},
                    'push': {'activeMonitors': 1, 'raw': 'q'*12000},
                    'history': {'raw': 'h'*24000},
                    'details': {'raw': 'd'*30000},
                    'decisionArchive': {'raw': 'a'*9000}},
                'comparisonEvidence': {'raw': 'r'*42000},
                'paperProfitEvidence': {'status': 'observed',
                    'strategyWinnerConfirmed': False},
                'simulationRuntimeBrief': {'status': 'observed',
                    'paper': {'accountsTotal': 11}},
                'entryBlockEvidence': {'status': 'observed',
                    'accounts': [{'profile': 'paper-00',
                                  'reasonCounts': [{'code': 'source-not-fresh',
                                                   'checks': 20}]}]},
            },
        }
        original = copy.deepcopy(source)
        report = diagnostics.bounded_report(source, 9500)
        sim = report['areas']['simulationAndPush']
        self.assertEqual(sim['status'], 'observed')
        self.assertTrue(sim['truncated'])
        self.assertEqual(len(sim['accounts']), 11)
        self.assertEqual(sim['accounts'][0]['cash'], 800)
        self.assertEqual(sim['accounts'][0]['checkedAt'], 1794603599987)
        self.assertEqual(sim['accounts'][0]['lastTradingEntryBlockCode'],
                         'source-not-fresh')
        self.assertEqual(sim['accounts'][0]['recentCases']['status'], 'unavailable')
        self.assertEqual(sim['accounts'][0]['recentCases']['sourceStatus'], 'observed')
        self.assertEqual(sim['accounts'][0]['forwardEvidence']['status'], 'collecting')
        self.assertFalse(sim['accounts'][0]['forwardEvidence']['winnerConfirmed'])
        self.assertNotIn('raw', json.dumps(sim))
        self.assertIn('comparisonEvidence', report['omittedAreas'])
        self.assertNotIn('simulationAndPush', report['omittedAreas'])
        self.assertEqual(source, original)
        self.assertLessEqual(len(json.dumps(report, ensure_ascii=False,
            separators=(',', ':')).encode('utf-8')), 9500)

    def test_keep_unavailable_sources_unavailable_not_promote_to_observed(self):
        accounts = [{'profile': 'p%d' % i, 'status': 'running',
            'recentCases': {'status': 'unavailable', 'reason': 'source-failed',
                             'raw': 'x'*1000},
            'forwardEvidence': {'status': 'unavailable',
                                'raw': 'z'*1000}} for i in range(10)]
        original = {'areas': {'simulationAndPush': {
            'status': 'partial', 'accounts': accounts, 'history': {'raw': 'y'*7000}}}}
        report=diagnostics.bounded_report(original, 8000)
        sim=report['areas']['simulationAndPush']
        self.assertEqual(sim['status'], 'partial')
        self.assertEqual(len(sim['accounts']), 10)
        self.assertEqual(sim['accounts'][0]['recentCases']['sourceStatus'],
                         'unavailable')
        self.assertEqual(sim['accounts'][0]['forwardEvidence']['status'],
                         'unavailable')
        self.assertNotIn('simulationAndPush', report['omittedAreas'])


if __name__ == '__main__':
    unittest.main()
