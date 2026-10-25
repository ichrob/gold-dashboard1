"""Read-only SnapTrade DEGIRO instrument-catalogue probe safety checks."""
import copy
import unittest
from unittest.mock import patch

import snaptrade_bridge as bridge


class BrokerCatalogueProbeTests(unittest.TestCase):
    def setUp(self):
        self.config = bridge._CONFIG
        self.checked = bridge._CATALOG_LAST_ATTEMPT
        self.probe = copy.deepcopy(bridge._CATALOG_STATE)
        bridge._CATALOG_LAST_ATTEMPT = 0.0
        bridge._CATALOG_STATE.clear()
        bridge._CATALOG_STATE.update(code='NOT_TESTED')
        bridge._CONFIG = {'clientId': 'dummy-id', 'consumerKey': 'dummy-key', 'personalFreeConfirmed': True}

    def tearDown(self):
        bridge._CONFIG = self.config
        bridge._CATALOG_LAST_ATTEMPT = self.checked
        bridge._CATALOG_STATE.clear()
        bridge._CATALOG_STATE.update(self.probe)

    def test_empty_broker_catalog_does_not_confirm_any_gold_products(self):
        value = bridge.summarize_broker_catalog({'instruments': []})
        self.assertEqual(value['code'], 'CATALOG_EMPTY')
        self.assertEqual(value['historicalMatches'], [])
        self.assertFalse(value['completeGoldList'])
        self.assertFalse(value['tradeApproved'])
        self.assertFalse(value['accountTradabilityVerified'])

    def test_instrument_match_does_not_approve_trade_or_infer_full_gold_list(self):
        value = bridge.summarize_broker_catalog({'instruments': [
            {'symbol': 'DE000FG4JXV7.XSGA', 'tradeable': True},
            {'symbol': 'DE000FG4JXV7.BNPS', 'tradeable': None},
            {'symbol': 'SOME_OTHER_ASSET', 'tradeable': True},
        ]})
        self.assertEqual(value['code'], 'CATALOG_RETURNED')
        self.assertEqual(value['instrumentCount'], 3)
        self.assertEqual(value['historicalMatches'], [
            {'isin': 'DE000FG4JXV7', 'providerTradeable': None}])
        self.assertFalse(value['completeGoldList'])
        self.assertFalse(value['accountTradabilityVerified'])
        self.assertFalse(value['tradeApproved'])

    def test_catalog_is_strictly_read_only_and_broker_specific(self):
        self.assertTrue(bridge.permitted('/brokerages/DEGIRO/instruments'))
        for path in ('/brokerages/OTHER/instruments', '/brokerages/DEGIRO/orders',
                     '/brokerages/DEGIRO/instruments/123', '/trade/place'):
            self.assertFalse(bridge.permitted(path))

    def test_catalog_probe_is_manual_one_shot_with_daily_cache(self):
        response = {'instruments': [{'symbol': 'DE000FG4JXV7.XSGA', 'tradeable': True}]}
        with patch.object(bridge, 'load_config'), \
             patch.object(bridge, 'api_get', return_value=response) as get, \
             patch.object(bridge.time, 'monotonic', return_value=1000):
            first = bridge.probe_broker_catalog()['catalogProbe']
            second = bridge.probe_broker_catalog()['catalogProbe']
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], '/brokerages/DEGIRO/instruments')
        self.assertEqual(first, second)
        self.assertEqual(first['code'], 'CATALOG_RETURNED')
        self.assertFalse(first['tradeApproved'])

    def test_automatic_catalog_probe_runs_once_after_valid_holdings_read(self):
        before = copy.deepcopy(bridge._STATE)
        try:
            bridge._STATE.update(code='READ_OK')
            with patch.object(bridge, 'load_config'), \
                 patch.object(bridge, 'api_get', return_value={'instruments': []}) as get, \
                 patch('builtins.print'):
                self.assertTrue(bridge.auto_probe_catalog())
                self.assertFalse(bridge.auto_probe_catalog())
            get.assert_called_once()
            self.assertEqual(get.call_args.args[0], '/brokerages/DEGIRO/instruments')
            result = bridge.diagnostics()
            self.assertEqual(result['catalogProbe']['code'], 'CATALOG_EMPTY')
            self.assertEqual(result['catalogHistoricalMatchCount'], 0)
            self.assertFalse(result['catalogFullGoldListVerified'])
            self.assertFalse(result['catalogTradeApproved'])
        finally:
            bridge._STATE.clear()
            bridge._STATE.update(before)

    def test_no_automatic_catalog_probe_before_successful_holdings_read(self):
        before = copy.deepcopy(bridge._STATE)
        try:
            bridge._STATE.update(code='READY')
            with patch.object(bridge, 'api_get') as get:
                self.assertFalse(bridge.auto_probe_catalog())
            get.assert_not_called()
            self.assertEqual(bridge._CATALOG_STATE['code'], 'NOT_TESTED')
        finally:
            bridge._STATE.clear()
            bridge._STATE.update(before)

    def test_automatic_catalog_error_does_not_retry_every_minute(self):
        before = copy.deepcopy(bridge._STATE)
        try:
            bridge._STATE.update(code='READ_OK')
            with patch.object(bridge, 'load_config'), \
                 patch.object(bridge, 'api_get', side_effect=bridge.ReadError('ACCESS_DENIED')) as get, \
                 patch('builtins.print'):
                self.assertTrue(bridge.auto_probe_catalog())
                self.assertFalse(bridge.auto_probe_catalog())
            get.assert_called_once()
            self.assertEqual(bridge._CATALOG_STATE['code'], 'ACCESS_DENIED')
            self.assertFalse(bridge._CATALOG_STATE['tradeApproved'])
        finally:
            bridge._STATE.clear()
            bridge._STATE.update(before)

    def test_bad_provider_response_fails_closed(self):
        with self.assertRaises(bridge.ReadError) as raised:
            bridge.summarize_broker_catalog({'results': [{'symbol': 'DE000FG4JXV7'}]})
        self.assertEqual(raised.exception.code, 'INVALID_RESPONSE')

    def test_provider_failure_cannot_be_reported_as_empty_catalog(self):
        with patch.object(bridge, 'load_config'), \
             patch.object(bridge, 'api_get', side_effect=bridge.ReadError('PROVIDER_UNAVAILABLE')):
            result = bridge.probe_broker_catalog()['catalogProbe']
        self.assertEqual(result['code'], 'PROVIDER_UNAVAILABLE')
        self.assertFalse(result['completeGoldList'])
        self.assertFalse(result['tradeApproved'])


if __name__ == '__main__':
    unittest.main()
