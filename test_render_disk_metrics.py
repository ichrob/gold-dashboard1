import datetime
import os
import unittest
from unittest.mock import patch
import render_disk_metrics as metrics


class RenderDiskMetricsTests(unittest.TestCase):
    def series(self, at=1000, resource=metrics.RESOURCE, value=123):
        return [{'labels': [{'field': 'service', 'value': resource}], 'unit': 'B',
                 'values': [{'timestamp': datetime.datetime.fromtimestamp(at, datetime.timezone.utc).isoformat(), 'value': value}]}]

    def test_only_fresh_target_volume_observations(self):
        result = metrics.parse(self.series(), 1050)
        self.assertEqual(result['diskUsage'], 123)
        self.assertFalse(result['maintenanceBudgetApproved'])
        for data in (self.series(resource='other'), self.series(at=100), self.series(at=1100),
                     self.series(value=-1), self.series(value=float('nan')), self.series(value=True), {}):
            self.assertNotEqual(metrics.parse(data, 1050)['status'], 'observed')

    def test_missing_secret_does_not_call_network(self):
        with patch.dict(os.environ, {}, clear=True), patch('urllib.request.build_opener') as network:
            self.assertEqual(metrics.report()['status'], 'configuration-required')
            network.assert_not_called()

    def test_failure_does_not_expose_secret_or_exception(self):
        metrics._cache = None
        with patch.dict(os.environ, {'BOB_RENDER_METRICS_API_KEY': 'private-test-token'}), patch('urllib.request.build_opener', side_effect=RuntimeError('private-test-token')):
            self.assertEqual(metrics.report(), {'status': 'unavailable'})
