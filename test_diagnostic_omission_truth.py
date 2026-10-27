"""Response truncation is not a failed paper-case read."""
import copy
import json
import unittest

import bob_diagnostics as diagnostics


class OmissionTruthTests(unittest.TestCase):
    def test_size_omission_preserves_source_status_and_real_faults(self):
        for status, severity in [('observed', 'info'), ('unavailable', 'warning'),
                                 ('failed', 'warning'), ('partial', 'warning'),
                                 ('unexpected', 'warning')]:
            with self.subTest(status=status):
                source = {'areas': {'simulationAndPush': {'status': 'observed',
                    'accounts': [{'profile': 'test', 'recentCases': {
                        'status': status, 'items': [{'detail': 'x' * 10000}]}}]}}}
                original = copy.deepcopy(source)
                result = diagnostics.bounded_report(source, 2500)
                finding = next(x for x in result['summary']['attention']
                               if x['area'].endswith('.recentCases'))
                self.assertEqual(finding['severity'], severity)
                self.assertEqual(finding['meaning'], 'response-size-omission-not-source-failure')
                self.assertEqual(finding['sourceStatus'],
                                 'unknown' if status == 'unexpected' else status)
                self.assertEqual(source, original)
                self.assertLess(len(json.dumps(result).encode()), 2500)
                self.assertNotIn('x' * 100, json.dumps(result))

    def test_observed_omission_does_not_hide_independent_failure(self):
        result = diagnostics.summary({'simulationAndPush': {'accounts': [
            {'recentCases': {'status': 'unavailable', 'sourceStatus': 'observed',
                             'reason': 'omitted-response-size-limit'}}],
            'push': {'status': 'failed'}}})
        self.assertEqual(result['assessment'], 'needs-attention')
        self.assertEqual([x['severity'] for x in result['attention']], ['info', 'warning'])

    def test_plain_missing_data_stays_warning(self):
        result = diagnostics.summary({'simulationAndPush': {'accounts': [
            {'recentCases': {'status': 'unavailable'}}]}})
        self.assertEqual(result['assessment'], 'needs-attention')
        self.assertEqual(result['attention'][0]['severity'], 'warning')


if __name__ == '__main__':
    unittest.main()
