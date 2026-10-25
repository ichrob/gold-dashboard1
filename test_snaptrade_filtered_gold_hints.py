"""Existing weekly SnapTrade trade-coverage reads yield bounded Gold research hints."""
import unittest
import snaptrade_bridge as bridge

ACCOUNT = '22222222-2222-4222-8222-222222222222'
CONFIG={'clientId':'test','consumerKey':'key','personalFreeConfirmed':True}
A='DE000PJ8APE4'
B='DE000FG34XV8'


class FilteredHistoryResearchTests(unittest.TestCase):
    def test_existing_filtered_read_reuses_rows_without_extra_api_requests(self):
        activities=[
            {'id':'act-gold-1','type':'BUY','symbol':{'description':'BNP Gold Turbo Long',
                 'symbol':A},'trade_date':'2026-10-20','units':'1','price':'10.0'},
            {'id':'act-gold-2','type':'SELL','symbol':{'description':'SG Gold Mini Short',
                 'symbol':B},'trade_date':'2026-10-22','units':'-1','price':'11.0'},
            {'id':'act-factor','type':'BUY','symbol':{'description':'SG Gold Faktor Long',
                 'symbol':'DE000FG4JXV7'},'trade_date':'2026-10-22','units':'1'},
        ]
        observed=[]
        def get(path,config,params):
            observed.append((path,dict(params)))
            return {'data':activities,'pagination':{'total':3}}
        summary=bridge.read_trade_coverage(ACCOUNT,CONFIG,get=get)
        self.assertEqual(len(observed),1)
        self.assertTrue(observed[0][0].endswith('/activities'))
        self.assertEqual(observed[0][1]['type'],'BUY,SELL')
        self.assertEqual(summary['code'],'READ_OK')
        self.assertTrue(summary['completeFilteredTradeWindow'])
        hints=summary['goldHistoryHints']
        self.assertEqual(hints['candidateCount'],2)
        self.assertEqual({x['isin'] for x in hints['items']},{A,B})
        self.assertTrue(all(x['eligibleForTop3'] is False and x['tradeApproved'] is False
                            for x in hints['items']))
        forbidden=('units','price','amount','fee','key','externalReference','accountId')
        for x in hints['items']:
            self.assertTrue(all(k not in x for k in forbidden))
        self.assertFalse(summary['accountHistoryComplete'])
        self.assertFalse(summary['fifoEligible'])

if __name__ == '__main__':
    unittest.main()
