import unittest
from unittest.mock import patch
import future_estimate
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

    def snapshot_with(self, estimate):
        reference = dict(price=4172, at='2026-10-02T12:00:00+00:00', previousClose=4200,
                         kind='reference', changePct=-.66)
        with patch.object(m, '_cache', None), patch.object(m, 'fetch_spot', return_value=m.unavailable('XAU/USD')), patch.object(m, 'fetch_quote', return_value=reference), patch.object(future_estimate, 'current_estimate', return_value=estimate):
            return m.snapshot()['future']

    def test_released_estimate_preferred_without_claiming_validated_accuracy(self):
        q=self.snapshot_with(dict(available=True,priceUsd=4180,priceAt='2026-10-02T12:10:00+00:00',
                                  validation={'ready':False}))
        self.assertEqual(q['price'],4180)
        self.assertEqual(q['kind'],'calculated')
        self.assertFalse(q['validation']['ready'])
        self.assertFalse(q['isExchangeRealtime'])
        self.assertAlmostEqual(q['changePct'],(4180/4200-1)*100)

    def test_unavailable_estimate_keeps_dated_reference(self):
        q=self.snapshot_with(dict(available=False,reason='stale inputs'))
        self.assertEqual(q['kind'],'reference')
        self.assertEqual(q['at'],'2026-10-02T12:00:00+00:00')
        self.assertIn('pausiert',q['note'])

    def test_old_reference_close_does_not_supply_estimated_daily_change(self):
        q=self.snapshot_with(dict(available=True,priceUsd=4180,priceAt='2026-10-05T12:10:00+00:00'))
        self.assertIsNone(q['changePct'])

if __name__=='__main__': unittest.main()
