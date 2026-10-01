"""Exact-contract research must never become a spot trade recommendation."""
import unittest
from datetime import timedelta
from unittest.mock import patch
import product_quotes as q
import sg_quotes as sg
from test_sg_quotes import fixture, NOW, AT

ISIN = 'DE000FG309G0'
OLD = '2026-10-01T07:27:20Z'


def future_fixture():
    product, props, snapshot, _, fx = fixture()
    product.update(Isin=ISIN, Id=7032167, ProductClassificationId=47,
                   AssetNMP='C_CMX_GOLD_F_Z26', AssetRic='GCZ26',
                   AssetName='Gold Future Dec 2026', AssetIsin='XC0009656924')
    props[0]['Value'] = ISIN
    snapshot['instrument'].update(isin=ISIN, entityValue='339518150')
    snapshot['quote']['idInstrument'] = '339518150'
    u = snapshot['derivativesUnderlyingList']['list'][0]
    u['instrument'] = dict(entityType='FUTURE', entityValue='188570012')
    u['market'] = dict(idNotation=317423266, codeExchange='CXE')
    u['derivativesBarrierFigureList'] = dict(idNotationUnderlying=317423266,
        isoCurrencyUnderlying='USD', priceUnderlying=4191.4, datetimePriceUnderlying=OLD,
        datetimeCalculation=AT)
    return product, props, snapshot, fx


class FutureResearchTests(unittest.TestCase):
    def parse(self, data, now=NOW):
        return sg.parse_future_research(*data, ISIN, now)

    def test_dated_research_is_separate_and_uses_future_not_spot(self):
        result = self.parse(future_fixture())
        self.assertFalse(result['found']); self.assertFalse(result['eligible'])
        self.assertEqual(result['metadata']['contract'], 'GCZ26')
        for field in ('price', 'bid', 'ask', 'leverage', 'quoteAt'):
            self.assertNotIn(field, result)
        r = result['futureResearch']
        self.assertTrue(r['productQuoteFresh'])
        self.assertFalse(r['underlyingFresh']); self.assertFalse(r['analysisAvailable'])
        self.assertEqual(r['underlyingAgeSeconds'], 790)
        self.assertAlmostEqual(r['indicativeLeverage'], 4191.4*.884*.1/24.62)
        self.assertEqual(q.stamp(r['estimateAt']), q.stamp(OLD))
        self.assertFalse(q.freshness(result, NOW)['eligible'])

    def test_rollover_ric_isin_and_secondary_contract_mismatches_block(self):
        for key, value in [('AssetNMP', 'C_CMX_GOLD_F_G27'), ('AssetRic', 'GCG27'),
                           ('AssetIsin', 'OTHER'), ('AssetName', 'Gold Future Feb 2027')]:
            data = future_fixture(); data[0][key] = value
            with self.assertRaises(ValueError): self.parse(data)
        for area, key, value in [('instrument', 'entityValue', '1'),
                                 ('instrument', 'entityType', 'PRECIOUS_METAL'),
                                 ('market', 'idNotation', 1), ('market', 'codeExchange', 'OTHER')]:
            data = future_fixture(); data[2]['derivativesUnderlyingList']['list'][0][area][key] = value
            with self.assertRaises(ValueError): self.parse(data)

    def test_spot_parser_rejects_futures(self):
        product, props, snapshot, fx = future_fixture()
        with self.assertRaises(ValueError): sg.parse_snapshot(product, props, snapshot, fixture()[3], fx, ISIN, NOW)

    def test_missing_or_wrong_underlying_time_cannot_use_calculation_time(self):
        for value in (None, '2026-10-01T07:27:20', '2026-10-01T08:00:00Z'):
            data = future_fixture()
            f = data[2]['derivativesUnderlyingList']['list'][0]['derivativesBarrierFigureList']
            if value is None: del f['datetimePriceUnderlying']
            else: f['datetimePriceUnderlying'] = value
            result = self.parse(data)
            self.assertNotIn('underlyingPriceUsd', result['futureResearch'])
            self.assertNotIn('indicativeLeverage', result['futureResearch'])
        data = future_fixture()
        data[2]['derivativesUnderlyingList']['list'][0]['derivativesBarrierFigureList']['idNotationUnderlying'] = 1
        self.assertNotIn('underlyingPriceUsd', self.parse(data)['futureResearch'])

    def test_fx_each_time_and_quote_expiry_remove_estimates(self):
        for key in ('data_updated_at', 'effective_at'):
            for at in ('2026-10-01T06:00:00Z', '2026-10-01T08:00:00Z'):
                data = future_fixture()
                if key == 'effective_at': data[3][key]['EUR'] = at
                else: data[3][key] = at
                self.assertNotIn('indicativeLeverage', self.parse(data)['futureResearch'])
        r = q.freshness(self.parse(future_fixture()), NOW+timedelta(seconds=51))
        self.assertFalse(r['futureResearch']['productQuoteFresh'])
        self.assertNotIn('indicativeLeverage', r['futureResearch'])
        self.assertFalse(r['eligible'])

    def test_very_old_or_crossed_barrier_never_gets_estimate(self):
        for price, at in [(4191.4, '2026-10-01T06:00:00Z'), (4500, OLD)]:
            data = future_fixture()
            data[2]['derivativesUnderlyingList']['list'][0]['derivativesBarrierFigureList'].update(priceUnderlying=price, datetimePriceUnderlying=at)
            self.assertNotIn('indicativeLeverage', self.parse(data)['futureResearch'])

    def test_recent_future_price_still_cannot_use_spot_analysis(self):
        data = future_fixture()
        data[2]['derivativesUnderlyingList']['list'][0]['derivativesBarrierFigureList']['datetimePriceUnderlying'] = AT
        result = self.parse(data)
        self.assertTrue(result['futureResearch']['underlyingFresh'])
        self.assertFalse(result['eligible'])
        result['found'] = True
        self.assertFalse(q.freshness(result, NOW)['eligible'])

    def test_adapter_has_no_spot_request_and_keeps_quotes_when_fx_fails(self):
        product, props, snapshot, fx = future_fixture()
        with patch.object(sg, 'fetch_snapshot', return_value=snapshot), \
             patch.object(sg.future_estimate, 'ensure_collector'), \
             patch.object(sg.future_analysis, 'ensure_collector'), \
             patch.object(sg, 'market_input', side_effect=OSError('FX unavailable')) as inputs:
            result = sg.get_quote(product, props, ISIN)
        self.assertTrue(result['productVerified']); self.assertFalse(result['eligible'])
        self.assertEqual(result['futureResearch']['ask'], 24.62)
        inputs.assert_called_once_with('fx')
        with patch.object(q, 'issuer_json', side_effect=[product, props]), \
             patch.object(sg, 'get_quote', return_value=result) as enrich:
            self.assertEqual(q.get_sg_quote(ISIN)['metadata']['contract'], 'GCZ26')
        enrich.assert_called_once()


if __name__ == '__main__': unittest.main()
