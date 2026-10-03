import unittest
import market_cards as m

class MarketCardsTests(unittest.TestCase):
    def payload(self, **values):
        meta=dict(symbol='GCZ26.CMX', currency='USD', instrumentType='FUTURE', regularMarketPrice=4172.1,
                  regularMarketTime=1000, chartPreviousClose=4202.3)
        meta.update(values)
        return {'chart': {'result': [{'meta': meta}]}}

    def test_day_change(self):
        q=m.parse_quote(self.payload(), 'GCZ26.CMX', 1100)
        self.assertAlmostEqual(q['changePct'], -.718654, places=5)
        self.assertEqual(q['kind'], 'reference')

    def test_missing_close_is_not_zero(self):
        q=m.parse_quote(self.payload(chartPreviousClose=None), 'GCZ26.CMX', 1100)
        self.assertIsNone(q['changePct'])

    def test_wrong_contract_and_currency(self):
        for values in [dict(symbol='GC=F'), dict(currency='EUR')]:
            with self.assertRaises(ValueError):
                m.parse_quote(self.payload(**values), 'GCZ26.CMX', 1100)

    def test_invalid_price_time_and_close(self):
        for values in [dict(regularMarketPrice=True), dict(regularMarketPrice=float('nan')),
                       dict(regularMarketTime=1200)]:
            with self.assertRaises(ValueError):
                m.parse_quote(self.payload(**values), 'GCZ26.CMX', 1100)
        self.assertIsNone(m.parse_quote(self.payload(chartPreviousClose=0), 'GCZ26.CMX', 1100)['changePct'])

    def test_positive_and_unchanged(self):
        self.assertGreater(m.parse_quote(self.payload(regularMarketPrice=4300), 'GCZ26.CMX', 1100)['changePct'],0)
        self.assertEqual(m.parse_quote(self.payload(regularMarketPrice=4202.3), 'GCZ26.CMX', 1100)['changePct'],0)

if __name__=='__main__': unittest.main()
