import unittest
import snaptrade_trade_insights as insights


class InsightsTests(unittest.TestCase):
    def account(self):
        return {
            'positions': [
                {'symbol': 'GOLD.A', 'currency': 'EUR', 'isin': 'DE000FG309G0',
                 'csvEvidence': {'source': 'explicit-owner-reconciliation'}},
                {'symbol': 'UNKNOWN', 'currency': 'CHF', 'isin': None},
            ],
            'journal': {
                'orders': {'code': 'READ_OK', 'checkedAt': '2026-10-21T10:00:00+00:00',
                           'rows': [
                               {'key': 'order-1', 'symbol': 'GOLD.A', 'name': 'Gold KO',
                                'currency': 'EUR', 'type': 'BUY', 'status': 'FILLED',
                                'date': '2026-10-21T10:01:05+00:00',
                                'executedAt': '2026-10-21T10:01:05+00:00',
                                'quantity': '10', 'price': '13.2'},
                               {'key': 'order-2', 'symbol': 'UNKNOWN', 'currency': 'CHF',
                                'type': 'SELL', 'status': 'CANCELED',
                                'date': '2026-10-21', 'quantity': '2', 'price': '8'},
                               {'key': 'order-3', 'symbol': 'GOLD.A', 'currency': 'EUR',
                                'type': 'BUY', 'status': 'OPEN', 'quantity': '0',
                                'price': '12', 'date': None},
                           ]},
                'activities': {'code': 'READ_OK', 'checkedAt': '2026-10-21T00:00:00+00:00',
                               'complete': False, 'rows': [
                                   {'currency': 'EUR', 'fee': '1.25'},
                                   {'currency': 'EUR', 'fee': '-0.10'},
                                   {'currency': 'CHF', 'fee': '2.0'},
                                   {'currency': '', 'fee': '19'},
                                   {'currency': 'EUR', 'fee': None}]},
            },
        }

    def test_fills_are_candidates_only(self):
        result = insights.read_account(self.account())
        self.assertEqual(result['executionsCount'], 2)
        self.assertEqual(result['readyForHistoricalComparison'], 1)
        first, second = result['executions']
        self.assertEqual(first['isin'], 'DE000FG309G0')
        self.assertTrue(first['reviewReady'])
        self.assertIsNone(first['realizedProfit'])
        self.assertFalse(first['productApproval'])
        self.assertFalse(first['automaticTrade'])
        self.assertIsNone(second['isin'])
        self.assertIsNone(second['executedAt'])
        self.assertFalse(second['reviewReady'])
        self.assertFalse(result['activitiesComplete'])

    def test_strict_provider_order_activity_matching_and_reported_fees(self):
        account=self.account()
        activity={'key':'activity-1','isin':'DE000FG309G0',
                  'type':'BUY','date':'2026-10-21','quantity':'10',
                  'price':'13.2','currency':'EUR','securityCurrency':'EUR',
                  'fee':'1.25','symbol':'GOLD.A'}
        account['journal']['activities']['rows']=[activity]
        report=insights.read_account(account)['reconciliation']
        self.assertEqual(report['status'],'available')
        self.assertEqual(report['candidatePairs'],1)
        self.assertEqual(report['ambiguousGroups'],0)
        self.assertEqual(report['pairs'][0]['isin'],'DE000FG309G0')
        self.assertEqual(report['pairs'][0]['reportedActivityFee'],'1.25')
        self.assertEqual(report['reportedMatchedFeesByCurrency'],[{
            'currency':'EUR','sumAsReported':'1.25','entries':1,
            'missingFeeEntries':0,
            'coverage':'matched-provider-activities-only-not-total-fees'}])
        self.assertFalse(report['accountHistoryComplete'])
        self.assertFalse(report['netProfitVerified'])
        self.assertFalse(report['learningEligible'])
        self.assertFalse(report['ordersEnabled'])
        self.assertIsNone(report['pairs'][0]['realizedProfit'])
        self.assertIsNone(report['pairs'][0]['netProfit'])
        self.assertFalse(report['pairs'][0]['productApproval'])

    def test_ambiguous_and_missing_evidence_never_becomes_execution(self):
        account=self.account()
        activity={'key':'activity-1','isin':'DE000FG309G0','type':'BUY',
                  'date':'2026-10-21','quantity':'10','price':'13.2',
                  'currency':'EUR','securityCurrency':'EUR','fee':None}
        account['journal']['activities']['rows']=[activity]
        first=account['journal']['orders']['rows'][0]
        account['journal']['orders']['rows'].append({**first, 'key':'another-order'})
        report=insights.read_account(account)['reconciliation']
        self.assertEqual(report['candidatePairs'],0)
        self.assertEqual(report['ambiguousGroups'],1)
        self.assertEqual(report['reportedMatchedFeesByCurrency'],[])
        account['journal']['orders']['rows'].pop()
        account['journal']['orders']['rows'][0].pop('executedAt')
        self.assertEqual(insights.read_account(account)['reconciliation']['candidatePairs'],0)
        # Placement-only time must never stand in for the execution instant.
        self.assertIsNone(insights.read_account(account)['executions'][0]['executedAt'])
        account['journal']['orders']['rows'][0]['executedAt']='2026-10-21T10:01:05+00:00'
        activity['price']='13.21'
        self.assertEqual(insights.read_account(account)['reconciliation']['candidatePairs'],0)
        activity['price']='13.2'
        activity['isin']=None
        self.assertEqual(insights.read_account(account)['reconciliation']['candidatePairs'],0)

    def test_signed_sell_and_missing_fee_only_reported_as_candidates(self):
        account=self.account()
        account['journal']['orders']['rows']=[{
            'key':'sale-1','symbol':'GOLD.A','name':'Gold KO','currency':'EUR',
            'type':'SELL','status':'PARTIALLY_FILLED','quantity':'4',
            'price':'15','date':'2026-10-21T11:03:00+00:00',
            'executedAt':'2026-10-21T11:03:00+00:00'
        }]
        account['journal']['activities']['rows']=[{
            'key':'trade-1','isin':'DE000FG309G0','type':'SELL',
            'date':'2026-10-21','quantity':'-4','price':'15',
            'currency':'EUR','fee':None
        }]
        report=insights.read_account(account)['reconciliation']
        self.assertEqual(report['candidatePairs'],1)
        self.assertEqual(report['pairs'][0]['side'],'SELL')
        self.assertEqual(report['pairs'][0]['quantity'],'4')
        self.assertIsNone(report['pairs'][0]['reportedActivityFee'])
        self.assertEqual(report['reportedMatchedFeesByCurrency'][0]['missingFeeEntries'],1)
        account['journal']['activities']['code']='UNAVAILABLE'
        report=insights.read_account(account)['reconciliation']
        self.assertEqual(report['status'],'unavailable')
        self.assertEqual(report['candidatePairs'],0)

    def test_journal_keeps_original_executed_vs_placed_times_separate(self):
        from snaptrade_portfolio import journal_rows
        item=journal_rows([{
            'brokerage_order_id':'provider-test-1','status':'EXECUTED',
            'filled_quantity':'1','action':'BUY',
            'time_placed':'2026-10-20T15:00:00+00:00',
            'time_executed':None, 'execution_price':10,
        }], 'orders', lambda n: str(n) if n is not None else None,
           lambda n,*args: n if isinstance(n,str) else '')[0]
        self.assertEqual(item['date'],'2026-10-20T15:00:00+00:00')
        self.assertIsNone(item['executedAt'])
        item=journal_rows([{
            'brokerage_order_id':'provider-test-2','status':'EXECUTED',
            'filled_quantity':'1','action':'BUY',
            'time_placed':'2026-10-20T15:00:00+00:00',
            'time_executed':'2026-10-20T15:04:00+00:00', 'execution_price':10,
        }], 'orders', lambda n: str(n) if n is not None else None,
           lambda n,*args: n if isinstance(n,str) else '')[0]
        self.assertEqual(item['executedAt'],'2026-10-20T15:04:00+00:00')

    def test_fees_are_not_invented_or_converted(self):
        result = insights.read_account(self.account())
        self.assertEqual(result['feesByCurrency'], [
            {'currency': 'CHF', 'reportedFeeSum': '2.0', 'entries': 1},
            {'currency': 'EUR', 'reportedFeeSum': '1.15', 'entries': 2},
        ])

    def test_conflicts_do_not_prove_instrument(self):
        account = self.account()
        account['positions'].append({'symbol': 'GOLD.A', 'currency': 'EUR',
                                     'isin': 'DE000FG14AV8', 'csvEvidence': {}})
        # Multiple distinct evidence-bearing ISINs with one provider symbol.
        account['positions'][-1]['csvEvidence'] = {'confirmed': True}
        self.assertIsNone(insights.read_account(account)['executions'][0]['isin'])

    def test_unconfirmed_and_stale_orders_are_not_called_live(self):
        account = self.account()
        account['journal']['orders']['code'] = 'UNAVAILABLE'
        result = insights.read_account(account)
        self.assertFalse(result['ordersAvailable'])
        self.assertEqual(result['executionsCount'], 2)
        self.assertFalse(insights.decimal('NaN'))
        self.assertIsNone(insights.execution_time('2026-10-21'))
        self.assertIsNone(insights.execution_time('invalid-date'))

    def test_duplicate_order_and_zero_fill(self):
        account = self.account()
        account['journal']['orders']['rows'].append(dict(account['journal']['orders']['rows'][0]))
        result = insights.read_account(account)
        self.assertEqual(result['executionsCount'], 2)


if __name__ == '__main__':
    unittest.main()
