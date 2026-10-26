"""One-shot account-scoped SnapTrade symbol-search tests; no provider calls."""
import copy
import unittest
from unittest.mock import patch
import snaptrade_bridge as bridge

ACCOUNT='917c8734-8470-4a3e-a18f-57c3f2ee6631'
TARGET='DE000FG4JXV7'

class AccountSymbolProbeTests(unittest.TestCase):
    def setUp(self):
        self.before=(bridge._CONFIG,bridge._SYMBOL_ACCOUNT_ID,bridge._SYMBOL_PROBED,
                     copy.deepcopy(bridge._SYMBOL_STATE),copy.deepcopy(bridge._STATE),
                     bridge._GENERATION)
        bridge._CONFIG={'clientId':'test-client','consumerKey':'test-consumer','personalFreeConfirmed':True}
        bridge._SYMBOL_ACCOUNT_ID=ACCOUNT
        bridge._SYMBOL_PROBED=False
        bridge._SYMBOL_STATE.clear()
        bridge._SYMBOL_STATE.update(code='NOT_TESTED')
        bridge._STATE.update(code='READ_OK')

    def tearDown(self):
        (bridge._CONFIG,bridge._SYMBOL_ACCOUNT_ID,bridge._SYMBOL_PROBED,
         states,current,bridge._GENERATION)=self.before
        bridge._SYMBOL_STATE.clear()
        bridge._SYMBOL_STATE.update(states)
        bridge._STATE.clear()
        bridge._STATE.update(current)

    def test_one_search_once_after_broker_read_not_trade(self):
        calls=[]
        def search(aid, config, substring):
            calls.append((aid,substring))
            return [{'raw_symbol': TARGET,'tradeable':True}]
        self.assertTrue(bridge.auto_probe_account_symbol(search))
        self.assertFalse(bridge.auto_probe_account_symbol(search))
        self.assertEqual(calls,[(ACCOUNT,TARGET)])
        status=bridge.status()['accountSymbolProbe']
        self.assertEqual(status['code'],'EXACT_SYMBOL_CANDIDATE')
        self.assertFalse(status['accountTradabilityVerified'])
        self.assertFalse(status['tradeApproved'])
        self.assertEqual(bridge.diagnostics()['accountSymbolProbe']['exactSymbolCandidates'],1)
        self.assertNotIn(ACCOUNT,str(bridge.diagnostics()))

    def test_no_query_without_readiness_or_unique_account(self):
        with patch.object(bridge,'api_search_account_symbol') as search:
            bridge._STATE['code']='READY'
            self.assertFalse(bridge.auto_probe_account_symbol())
            bridge._STATE['code']='READ_OK'
            bridge._SYMBOL_ACCOUNT_ID=None
            self.assertFalse(bridge.auto_probe_account_symbol())
            search.assert_not_called()

    def test_failure_never_claims_empty_catalog_or_retries_immediately(self):
        calls=[]
        def fail(*args):
            calls.append(1)
            raise bridge.ReadError('RATE_LIMITED')
        self.assertTrue(bridge.auto_probe_account_symbol(fail))
        self.assertFalse(bridge.auto_probe_account_symbol(fail))
        self.assertEqual(len(calls),1)
        self.assertEqual(bridge.status()['accountSymbolProbe']['code'],'RATE_LIMITED')
        self.assertFalse(bridge.status()['accountSymbolProbe']['tradeApproved'])

    def test_symbols_only_not_orders_and_account_path_locked(self):
        with self.assertRaises(bridge.ReadError) as e:
            bridge.api_search_account_symbol('not-a-uuid',bridge._CONFIG,TARGET)
        self.assertEqual(e.exception.code,'PATH_REJECTED')
        with self.assertRaises(bridge.ReadError):
            bridge.api_search_account_symbol(ACCOUNT,bridge._CONFIG,'GOLD')
        self.assertFalse(bridge.permitted('/accounts/'+ACCOUNT+'/orders/place'))
        self.assertFalse(bridge.permitted('/accounts/'+ACCOUNT+'/symbols')) # POST only, not GET
        self.assertFalse(bridge.status()['realOrders'])


if __name__=='__main__':
    unittest.main()
