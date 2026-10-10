import unittest
from unittest.mock import patch
import future_estimate
import auto_collection
from datetime import datetime, timezone, timedelta
import market_cards as m

class MarketCardsTests(unittest.TestCase):
    def setUp(self):
        market=patch.object(m.background_push,'gold_weekend_seconds_remaining',return_value=0)
        market.start();self.addCleanup(market.stop)

    def test_weekend_quiet_source_cards_preserve_original_estimate(self):
        with patch.object(m.background_push,'gold_weekend_seconds_remaining',return_value=3600), \
             patch.object(m,'_cache',None),patch.object(m,'fetch_spot') as spot, \
             patch.object(m,'fetch_quote') as future,patch.object(m.investing_card,'fetch') as cfd, \
             patch.object(m,'last_estimate',return_value=None) as archive:
            result=m.snapshot()
            spot.assert_not_called();future.assert_not_called();cfd.assert_not_called()
            archive.assert_called_once()
            self.assertIn('geschlossen',result['spot']['note'])
            self.assertIsNone(result['future']['price'])

    def payload(self, **values):
        meta=dict(symbol='GCZ26.CMX', currency='USD', instrumentType='FUTURE', regularMarketPrice=4172.1,
                  regularMarketTime=1000, chartPreviousClose=4202.3)
        meta.update(values)
        return {'chart': {'result': [{'meta': meta}]}}

    def test_cached_friday_cards_are_frozen_not_falsely_realtime(self):
        friday=dict(spot=dict(price=4100.,at='2026-10-09T21:01:14+00:00',kind='spot'),
                    cfd=dict(price=4101.,at='2026-10-09T21:01:14+00:00',realtimeCfd=True,kind='cfd'),
                    future=dict(price=4102.,at='2026-10-09T21:01:14+00:00'),
                    estimate=dict(price=4103.,at='2026-10-09T21:01:14+00:00'),
                    sessionAdvisory=None)
        with patch.object(m.background_push,'gold_weekend_seconds_remaining',return_value=3600),patch.object(m,'_cache',friday),patch.object(m,'fetch_spot') as fetch:
            frozen=m.snapshot()
        self.assertTrue(frozen['cfd']['marketClosed'])
        self.assertFalse(frozen['cfd']['realtimeCfd'])
        self.assertEqual(frozen['spot']['at'],friday['spot']['at'])
        self.assertTrue(friday['cfd']['realtimeCfd'])
        fetch.assert_not_called()

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
        with patch.object(m.investing_card, 'fetch', return_value=m.unavailable('Gold CFD')), patch.object(m, '_cache', None), patch.object(m, 'fetch_spot', return_value=m.unavailable('XAU/USD')), patch.object(m, 'fetch_quote', return_value=reference), patch.object(future_estimate, 'current_estimate', return_value=estimate):
            return m.snapshot()

    def test_released_estimate_preferred_without_claiming_validated_accuracy(self):
        q=self.snapshot_with(dict(available=True,priceUsd=4180,priceAt='2026-10-02T12:10:00+00:00',
                                  validation={'ready':False}))
        self.assertEqual(q['future']['price'],4172)
        self.assertEqual(q['future']['kind'],'reference')
        q=q['estimate']
        self.assertEqual(q['price'],4180)
        self.assertEqual(q['kind'],'calculated')
        self.assertFalse(q['validation']['ready'])
        self.assertFalse(q['isExchangeRealtime'])
        self.assertAlmostEqual(q['changePct'],(4180/4200-1)*100)

    def test_unavailable_estimate_keeps_dated_reference(self):
        q=self.snapshot_with(dict(available=False,reason='stale inputs'))
        self.assertIsNone(q['estimate']['price'])
        self.assertIn('pausiert',q['estimate']['note'])
        q=q['future']
        self.assertEqual(q['kind'],'reference')
        self.assertEqual(q['at'],'2026-10-02T12:00:00+00:00')

    def test_old_reference_close_does_not_supply_estimated_daily_change(self):
        q=self.snapshot_with(dict(available=True,priceUsd=4180,priceAt='2026-10-05T12:10:00+00:00'))
        self.assertIsNone(q['estimate']['changePct'])

    def test_last_frozen_estimate_restores_with_original_time(self):
        now=datetime.now(timezone.utc)
        original=(now-timedelta(days=1)).isoformat()
        saved=dict(contract='GCZ26',priceUsd=4188.25,priceAt=original)
        with patch.object(auto_collection,'status',return_value={'archive':{'latestEstimate':saved}}):
            q=m.last_estimate(now=now.timestamp())
        self.assertEqual(q['price'],4188.25)
        self.assertEqual(q['at'],original)
        self.assertTrue(q['historical'])
        self.assertIsNone(q['changePct'])

    def test_newer_memory_estimate_wins_and_invalid_archive_is_not_shown(self):
        now=datetime.now(timezone.utc)
        previous=dict(price=4190,at=(now-timedelta(minutes=5)).isoformat(),kind='calculated')
        for age,contract in ((8,'GCZ26'),(-1,'GCZ26'),(1,'GC=F')):
            saved=dict(contract=contract,priceUsd=9999,priceAt=(now-timedelta(days=age)).isoformat())
            with patch.object(auto_collection,'status',return_value={'archive':{'latestEstimate':saved}}):
                self.assertIsNone(m.last_estimate(now=now.timestamp()))
                self.assertEqual(m.last_estimate(previous,now.timestamp())['price'],4190)

    def test_unavailable_calculation_displays_saved_value_then_new_calculation_replaces_it(self):
        original='2026-10-02T12:00:00+00:00'
        historical=dict(price=4170,at=original,kind='calculated',historical=True)
        with patch.object(m,'last_estimate',return_value=historical) as old:
            result=self.snapshot_with(dict(available=False))
            self.assertEqual(result['estimate']['price'],4170)
            self.assertEqual(result['estimate']['at'],original)
            old.assert_called_once()
        with patch.object(m,'last_estimate') as old:
            result=self.snapshot_with(dict(available=True,priceUsd=4180,priceAt='2026-10-02T12:10:00+00:00'))
            self.assertEqual(result['estimate']['price'],4180)
            self.assertFalse(result['estimate'].get('historical',False))
            old.assert_not_called()

    def test_malformed_source_does_not_hide_other_cards(self):
        with patch.object(m,'_cache',None),patch.object(m,'fetch_spot',side_effect=AttributeError('bad source')),patch.object(m,'fetch_quote',return_value={'price':4172,'kind':'reference'}),patch.object(future_estimate,'current_estimate',return_value={'available':False}),patch.object(m,'last_estimate',return_value=None):
            self.assertEqual(m.snapshot()['future']['price'],4172)
        for at in (None,{},42):
            with self.assertRaises(ValueError):future_estimate.stamp(at)

if __name__=='__main__': unittest.main()
