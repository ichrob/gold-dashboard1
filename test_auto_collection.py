import base64
import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import auto_collection as a
import estimate_quality as quality
import test_auth as baseline

NOW = datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc)


class AutoCollectionTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('_research', {}), ('_next_source', 0), ('_failures', 0), ('_report', {})):
            p = patch.object(a, name, value); p.start(); self.addCleanup(p.stop)

    def test_window_handles_swiss_dst_and_weekends(self):
        self.assertTrue(a.in_window(NOW))
        self.assertFalse(a.in_window(NOW.replace(hour=20)))
        self.assertFalse(a.in_window(NOW+timedelta(days=1)))
        # Switzerland is UTC+1 in December: 05 UTC is 06 local.
        self.assertTrue(a.in_window(datetime(2026, 12, 1, 5, tzinfo=timezone.utc)))
        self.assertFalse(a.in_window(datetime(2026, 12, 1, 4, tzinfo=timezone.utc)))

    def test_collection_and_archive_evaluation_need_no_browser(self):
        research = dict(contract='GCZ26', underlyingAt=NOW.isoformat())
        out = dict(available=True, validation={'ready': True}, collection={'sampleCount': 20})
        with patch.object(a, 'enabled', return_value=True), patch.object(a.future_estimate, 'ensure_collector') as collect, patch.object(a.product_quotes, 'get_sg_quote', return_value={'futureResearch': research}) as source, patch.object(a.future_estimate, 'current_estimate', return_value=out), patch.object(a.bob_validation_store, 'request', return_value={'pairs': [], 'diagnostics': {'pairCount': 20}}), patch.object(a.bob_market_store, 'request', return_value={'diagnostics': {'sampleCount': 100}}), patch.object(a.estimate_quality, 'restore_durable') as restore, patch.object(a.estimate_quality, 'quality', return_value={'ready': True}), patch.object(a, 'datetime') as clock:
            clock.now.return_value = NOW
            a.tick(NOW)
            self.assertEqual(a.status()['state'], 'ready')
            self.assertEqual(a.status()['archive']['pairCount'], 20)
            self.assertEqual(len(a.status()['horizons']), 4)
            collect.assert_called_once()
            source.assert_called_once_with('DE000FG309G0')
            restore.assert_called_once_with([], NOW)
            # A second spot cycle keeps the actual reference; it does not
            # increase the SG request cadence or rewrite source timestamps.
            a.tick(NOW+timedelta(seconds=30))
            source.assert_called_once()
            self.assertEqual(a.status()['referenceAt'], NOW.isoformat())

    def test_source_failure_uses_backoff_without_alternative_provider(self):
        with patch.object(a, 'enabled', return_value=True), patch.object(a.future_estimate, 'ensure_collector'), patch.object(a.product_quotes, 'get_sg_quote', return_value={'sourceFailure': True}) as source, patch.object(a.future_estimate, 'current_estimate', return_value={'available': False}), patch.object(a.bob_validation_store, 'request', return_value={'pairs': []}), patch.object(a.bob_market_store, 'request', return_value={}), patch.object(a.estimate_quality, 'restore_durable'), patch.object(a, 'datetime') as clock:
            clock.now.return_value = NOW
            a.tick(NOW)
            self.assertGreaterEqual(a.status()['nextSourceInSeconds'], 299)
            self.assertFalse(a.status()['ready'])
            a.tick(NOW)
            source.assert_called_once()

    def test_missing_current_estimate_or_failed_archive_never_grants_readiness(self):
        for estimate in ({'available': False}, {'available': True, 'validation': {'ready': True}}):
            with patch.object(a, 'enabled', return_value=True), patch.object(a.future_estimate, 'ensure_collector'), patch.object(a.product_quotes, 'get_sg_quote', return_value={'futureResearch': {'contract': 'GCZ26'}}), patch.object(a.future_estimate, 'current_estimate', return_value=estimate), patch.object(a.bob_validation_store, 'request', side_effect=OSError('fixture')), patch.object(a, 'datetime') as clock:
                clock.now.return_value = NOW
                a.tick(NOW)
                self.assertFalse(a.status()['ready'])

    def test_disabled_and_outside_window_do_not_poll_and_clear_readiness(self):
        with patch.object(a, 'enabled', return_value=False), patch.object(a.product_quotes, 'get_sg_quote') as source:
            a.tick(NOW); source.assert_not_called()
        a._report = {'ready': True}
        with patch.object(a, 'enabled', return_value=True), patch.object(a.product_quotes, 'get_sg_quote') as source:
            a.tick(NOW.replace(hour=21)); source.assert_not_called()
            self.assertFalse(a.status()['ready'])
            self.assertEqual(a.status()['state'], 'paused')

    def test_status_copy_and_public_health_exclude_private_measurements(self):
        a._report = {'archive': {'pairCount': 22}, 'horizons': [{'meanAbsoluteError': 1}], 'ready': True}
        copy = a.status(); copy['archive']['pairCount'] = 999
        self.assertEqual(a.status()['archive']['pairCount'], 22)
        self.assertNotIn('archive', a.health()); self.assertNotIn('horizons', a.health())


class CollectionEndpointTests(unittest.TestCase):
    request = baseline.AuthenticationTests.request
    setUp = baseline.AuthenticationTests.setUp
    @classmethod
    def setUpClass(cls):
        baseline.AuthenticationTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        baseline.AuthenticationTests.tearDownClass.__func__(cls)
    def test_measurement_endpoint_requires_auth_and_responds_without_network(self):
        self.assertEqual(self.request('GET', '/api/collection-status')[0], 401)
        basic = 'Basic '+base64.b64encode(b'test-user:test-only-password').decode()
        with patch.object(a, 'status', return_value={'enabled': True, 'archive': {'pairCount': 20}}):
            status, headers, body, _ = self.request('GET', '/api/collection-status', headers={'Authorization': basic})
            self.assertEqual(status, 200)
            self.assertIn(b'"pairCount":20', body)
            self.assertEqual(headers['Cache-Control'], 'no-store')
