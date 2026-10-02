import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from unittest.mock import patch
import future_analysis as f
import auto_collection as a

KEY = ('5m', '5d')
NOW = datetime(2026, 10, 2, 17, 30, tzinfo=timezone.utc)

class RecoveryTests(unittest.TestCase):
    def test_shared_cooldown_is_not_extended_by_consumers(self):
        error = HTTPError('https://example.test', 429, 'private body', {'Retry-After': '1200'}, None)
        with patch.object(f, '_chart_cache', {}), patch.object(f, '_chart_retry', {}), patch.object(f, '_chart_failures', {}), patch.object(f, '_chart_errors', {}), patch.object(f.time, 'monotonic', return_value=100) as clock, patch.object(f, '_fetch_chart', side_effect=error) as fetch:
            with self.assertRaises(HTTPError): f.fetch_chart('5m', '5d')
            self.assertEqual(f.reference_failure(error), (1200, 'GCZ26-Historie: Datenanbieter antwortet mit HTTP 429'))
            clock.return_value = 1298
            with self.assertRaises(URLError) as wait: f.fetch_chart('5m', '5d')
            self.assertEqual(f.reference_failure(wait.exception)[0], 2)
            self.assertEqual(f._chart_retry[KEY], 1300)
            fetch.assert_called_once()
            clock.return_value = 1300
            fetch.side_effect = None; fetch.return_value = {'provider': 'recovered'}
            self.assertEqual(f.fetch_chart('5m', '5d'), {'provider': 'recovered'})
            self.assertNotIn(KEY, f._chart_errors)

    def test_stale_download_uses_normal_poll_without_relaxing_freshness(self):
        with patch.object(f, '_chart_retry', {}):
            delay, message = f.reference_failure(ValueError('GCZ26-Handelsdaten zu alt oder Kurszeit zukünftig'))
            self.assertEqual(delay, 60)
            self.assertIn('zu alt', message)

    def test_blocked_fallback_preserves_primary_error_and_remaining_wait(self):
        primary = URLError('private cooldown details')
        with patch.object(a, '_research', {}), patch.object(a, '_next_source', 0), patch.object(a, '_failures', 7), patch.object(a, 'enabled', return_value=True), patch.object(a.future_estimate, 'ensure_collector'), patch.object(f, '_chart_retry', {KEY: 102}), patch.object(f, '_chart_errors', {KEY: 'GCZ26-Historie: Datenanbieter antwortet mit HTTP 429'}), patch.object(f.time, 'monotonic', return_value=100), patch.object(f, 'fetch_reference', side_effect=primary), patch.object(a.sg_quotes, 'fetch_future_reference', side_effect=PermissionError('ONVISTA_AUTOMATION_NOT_APPROVED')), patch.object(a.future_estimate, 'current_estimate', return_value={'available': False}), patch.object(a.bob_validation_store, 'request', return_value={'pairs': []}), patch.object(a.bob_market_store, 'request', return_value={}), patch.object(a.estimate_quality, 'restore_durable'):
            a.tick(NOW)
            self.assertEqual(a._next_source, 102)
            self.assertEqual(a.status()['nextSourceInSeconds'], 2)
            self.assertIn('HTTP 429', a.status()['sourceStatus'])
            self.assertNotIn('private', a.status()['sourceStatus'])
            self.assertFalse(a.status()['ready'])

if __name__ == '__main__': unittest.main()
