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
