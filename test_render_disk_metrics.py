import datetime
import os
import unittest
from urllib.error import HTTPError, URLError
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

    def test_render_units_normalized_to_bytes_before_pilot_budget_check(self):
        for unit, value, expected in (
                ('B', 123, 123),
                ('bytes', 123.01, 124),
                ('MB', 750.000001, 750000001),
                ('GB', 0.75, 750000000),
                ('GB', 0.7500001, 750000100),
                ('GiB', 1, 1073741824)):
            with self.subTest(unit=unit, value=value):
                data = self.series(value=value)
                data[0]['unit'] = unit
                result = metrics.parse(data, 1050)
                self.assertEqual(result['status'], 'observed')
                self.assertEqual(result['diskUsage'], expected)
                self.assertIs(type(result['diskUsage']), int)
                self.assertEqual(result['unit'], 'bytes')
                self.assertEqual(result['reportedUnit'], unit)
                self.assertFalse(result['maintenanceBudgetApproved'])

    def test_unknown_or_implausible_units_are_never_migration_proof(self):
        for unit, value in (('mystery', 0.5), ('gb', 0.5), (None, 0.5),
                            ('GB', 2000), ('B', float('inf'))):
            with self.subTest(unit=unit, value=value):
                data = self.series(value=value)
                data[0]['unit'] = unit
                self.assertNotEqual(metrics.parse(data, 1050)['status'], 'observed')

    def test_missing_secret_does_not_call_network(self):
        with patch.dict(os.environ, {}, clear=True), patch('urllib.request.build_opener') as network:
            self.assertEqual(metrics.report()['status'], 'configuration-required')
            network.assert_not_called()

    def test_http_errors_expose_only_allowlisted_numeric_code(self):
        for status in (400, 401, 403, 404, 409, 429, 500, 502, 503, 418):
            with self.subTest(status=status):
                metrics._cache = None
                error = HTTPError('https://api.render.com/private-secret',
                                  status, 'SECRET-error-text', {}, None)
                with patch.dict(os.environ, {'BOB_RENDER_METRICS_API_KEY': 'private-test-token'}), \
                        patch('urllib.request.build_opener', side_effect=error):
                    result = metrics.report()
                self.assertEqual(result['status'], 'provider-http-error')
                self.assertEqual(result['httpStatus'],
                                 status if status in (400, 401, 403, 404, 409, 429, 500, 502, 503) else None)
                self.assertNotIn('SECRET', repr(result))
                self.assertNotIn('private', repr(result))

    def test_transport_error_exposes_no_credentials(self):
        metrics._cache = None
        with patch.dict(os.environ, {'BOB_RENDER_METRICS_API_KEY': 'private-test-token'}), \
                patch('urllib.request.build_opener',
                      side_effect=URLError('private-test-token')):
            self.assertEqual(metrics.report(), {'status': 'network-unavailable'})

    def test_failure_does_not_expose_secret_or_exception(self):
        metrics._cache = None
        with patch.dict(os.environ, {'BOB_RENDER_METRICS_API_KEY': 'private-test-token'}), patch('urllib.request.build_opener', side_effect=RuntimeError('private-test-token')):
            self.assertEqual(metrics.report(), {'status': 'unavailable'})
