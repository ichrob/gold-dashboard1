"""A trade-linked dim-screen lease is a read-only paired state, not broker control."""
import unittest
import android_remote as remote

class TradeDimState(unittest.TestCase):
    def test_only_one_real_active_trade_gets_opaque_receipt(self):
        result=remote.verified_trade_state(
            [('trade-original-1',{'active':True,'recordOnly':False})],2000000000)
        self.assertEqual(result['state'],'ACTIVE')
        self.assertEqual(len(result['tradeTag']),24)
        self.assertEqual(set(result),{'ok','state','tradeTag','checkedAt'})
        self.assertNotIn('trade-original-1',str(result))
        self.assertNotIn('isin',str(result).lower())
        self.assertEqual(result,remote.verified_trade_state(
            [('trade-original-1',{'active':True})],2000000000))
        self.assertNotEqual(result['tradeTag'],remote.verified_trade_state(
            [('trade-original-2',{'active':True})],2000000000)['tradeTag'])

    def test_closed_ambiguous_and_record_only_never_authorize_screen(self):
        self.assertEqual(remote.verified_trade_state([],1)['state'],'NO_ACTIVE')
        for rows in (
            [('t',{'active':False})],
            [('t',{'active':True,'recordOnly':True})],
            [('t',{'active':True}),('second',{'active':True})],
            [('t',{})],
        ):
            self.assertNotEqual(remote.verified_trade_state(rows,2)['state'],'ACTIVE')
            self.assertIsNone(remote.verified_trade_state(rows,2)['tradeTag'])

    def test_status_not_an_order_or_remote_navigation_action(self):
        self.assertNotIn('trade-status',remote.ACTIONS)
        self.assertNotIn('trade-status',remote.TOOLS)
        self.assertNotIn('buy',remote.ACTIONS)
        self.assertNotIn('place_order',remote.ACTIONS)

if __name__ == '__main__':
    unittest.main()
