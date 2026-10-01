import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import product_quotes as q
import sg_quotes as sg

ISIN = 'DE000FG4JXV7'
NOW = datetime(2026, 10, 1, 7, 40, 30, tzinfo=timezone.utc)
AT = '2026-10-01T07:40:20Z'


def fixture():
    product = dict(Id=7069123, ProductClassificationId=43, Isin=ISIN, ExchangeCode='CBDE',
                   AssetNMP='XAUUSD', AssetCurrency='USD', Currency='EUR', Status=65)
    props = [dict(Name='Isin', Value=ISIN), dict(Name='PutOrCall', Value='Put'),
             dict(Name='BarrierTurboCertificate', Value=4460, Suffix=' USD'),
             dict(Name='Strike', Value=4460), dict(Name='Ratio', Value=10),
             # Deliberately outdated/undated metadata must not set live fields.
             dict(Name='Bid', Value=1), dict(Name='Offer', Value=2),
             dict(Name='CurrentLeverage', Value=99), dict(Name='TimeStamp', Value='1999-01-01')]
    snapshot = dict(instrument=dict(isin=ISIN, entityValue='340459583', name='SG Turbo',
                                    entitySubType='KNOCKOUT_CERTIFICATE'),
                    derivativesIssuer=dict(id=53159),
                    derivativesDetails=dict(isoCurrency='EUR', numberUnderlyings=1, quanto=False,
                                            hasIndicativeDetails=False, dataStatus=1,
                                            hasBarrierBeenHit=False, hasOnlyBidPrices=False,
                                            nameExerciseRight='PUT'),
                    quote=dict(idInstrument='340459583', isoCurrency='EUR',
                               market=dict(codeContributor='SGED', codeMarket='@_SGED', codeExchange='@DE'),
                               codeQualityPriceBidAsk='RLT', bid=24.61, ask=24.62,
                               volumeBid=10000, volumeAsk=10000, datetimeBid=AT, datetimeAsk=AT),
                    derivativesUnderlyingList=dict(list=[dict(isoCurrency='USD', coverRatio=.1,
                        instrument=dict(symbol='XAU', entityType='PRECIOUS_METAL'),
                        derivativesBarrierList=dict(list=[dict(typeBarrier=kind, barrier=4460,
                            isoCurrencyUnderlying='USD', hasBeenHit=False) for kind in ('KNOCK_OUT', 'STRIKE')]))]))
    spot = dict(stale=False, data_state=dict(status='fresh'),
                xau=dict(currency='USD', unit='troy_oz'), spot_usd_oz=4154, price_as_of=AT)
    fx = dict(result='success', base='USD', source='live', sources=dict(EUR='live'),
              market_session='open', rates=dict(EUR=.884), data_updated_at=AT, effective_at=dict(EUR=AT))
    return product, props, snapshot, spot, fx


class SgQuoteTests(unittest.TestCase):
    def parse(self, data, now=NOW):
        return sg.parse_snapshot(*data, ISIN, now)

    def test_dated_prices_and_calculated_gearing_ignore_undated_fields(self):
        result = self.parse(fixture())
        self.assertTrue(result['eligible'])
        self.assertEqual(result['bid'], 24.61)
        self.assertAlmostEqual(result['leverage'], 4154*.884*.1/24.62)
        self.assertEqual(result['leverageKind'], 'calculated-gearing')
        self.assertTrue(result['leverageEstimated'])
        self.assertEqual(result['ageSeconds'], 10)
        self.assertFalse(result['isDegiroQuote'])
        self.assertIn('kein SG-Hebelwert', result['leverageNote'])

    def test_each_source_input_must_be_dated_current_and_not_future(self):
        for kind, field in [(2, 'datetimeBid'), (2, 'datetimeAsk'), (3, 'price_as_of'),
                            (4, 'data_updated_at')]:
            for value in ['2026-10-01T07:00:00Z', '2026-10-01T08:00:00Z', '2026-10-01T07:40:20']:
                data = fixture()
                target = data[kind]['quote'] if kind == 2 else data[kind]
                target[field] = value
                if value.endswith('Z'):
                    self.assertFalse(self.parse(data)['eligible'], (kind, field, value))
                else:
                    with self.assertRaises(ValueError): self.parse(data)
        data = fixture(); data[4]['effective_at']['EUR'] = '2026-10-01T06:00:00Z'
        self.assertFalse(self.parse(data)['eligible'])
        data = fixture(); del data[3]['price_as_of']
        with self.assertRaises(KeyError): self.parse(data)

    def test_cached_calculation_expires_using_original_input_times(self):
        result = self.parse(fixture())
        self.assertFalse(q.freshness(result, NOW+timedelta(seconds=51))['eligible'])
        del result['fxAt']
        self.assertFalse(q.freshness(result, NOW)['eligible'])

    def test_identity_and_non_executable_quotes_rejected(self):
        for area, key, value in [('instrument', 'isin', 'DE000FG309G0'),
                                 ('instrument', 'entityValue', '1'), ('quote', 'idInstrument', '1'),
                                 ('quote', 'codeQualityPriceBidAsk', 'DLY'),
                                 ('quote', 'isoCurrency', 'USD'), ('quote', 'ask', 24),
                                 ('quote', 'volumeAsk', 0), ('quote', 'bid', float('nan')),
                                 ('derivativesDetails', 'quanto', True),
                                 ('derivativesDetails', 'hasBarrierBeenHit', True),
                                 ('derivativesDetails', 'hasOnlyBidPrices', True),
                                 ('derivativesDetails', 'numberUnderlyings', 2)]:
            data = fixture(); data[2][area][key] = value
            with self.assertRaises(ValueError, msg=(area, key)): self.parse(data)
        data = fixture(); data[2]['quote']['market']['codeContributor'] = 'OTHER'
        with self.assertRaises(ValueError): self.parse(data)

    def test_unsupported_and_inactive_products_rejected(self):
        for key, value in [('ProductClassificationId', 37), ('Status', 8), ('TodayBarrierHitDate', AT)]:
            data = fixture(); data[0][key] = value
            with self.assertRaises(ValueError): self.parse(data)

    def test_ratio_direction_and_authoritative_issuer_barrier(self):
        data = fixture(); data[2]['derivativesUnderlyingList']['list'][0]['coverRatio'] = 10
        with self.assertRaises(ValueError): self.parse(data)
        data = fixture(); data[2]['derivativesUnderlyingList']['list'][0]['derivativesBarrierList']['list'][0]['barrier'] = 4461
        result = self.parse(data)
        self.assertTrue(result['eligible'])
        self.assertEqual(result['ko'], 4460)
        self.assertTrue(result['secondaryMetadataDiffers'])
        data = fixture(); data[2]['derivativesDetails']['nameExerciseRight'] = 'CALL'
        with self.assertRaises(ValueError): self.parse(data)
        data = fixture(); data[3]['spot_usd_oz'] = 4500
        with self.assertRaises(ValueError): self.parse(data)

    def test_daily_fx_and_stale_gold_are_never_used(self):
        for kind, key, value in [(3, 'stale', True), (4, 'source', 'ecb_daily'),
                                  (4, 'market_session', 'weekend'), (4, 'base', 'EUR')]:
            data = fixture(); data[kind][key] = value
            with self.assertRaises(ValueError): self.parse(data)

    def test_weekend_and_end_of_trading_session_blocked(self):
        for at in [datetime(2026, 10, 3, 7, 40, 30, tzinfo=timezone.utc),
                   datetime(2026, 10, 1, 20, 0, 0, tzinfo=timezone.utc)]:
            data = fixture(); stamp = at.isoformat()
            data[2]['quote'].update(datetimeBid=stamp, datetimeAsk=stamp)
            data[3]['price_as_of'] = stamp
            data[4].update(data_updated_at=stamp, effective_at=dict(EUR=stamp))
            self.assertFalse(self.parse(data, at)['eligible'])

    def test_failed_extra_source_preserves_verified_metadata(self):
        product, props, *_ = fixture()
        with patch.object(sg, 'fetch_snapshot', side_effect=ValueError('Kursdaten fehlen')), \
             patch.object(sg, 'market_input', return_value={}):
            result = sg.get_quote(product, props, ISIN)
        self.assertTrue(result['productVerified']); self.assertFalse(result['eligible'])
        self.assertEqual(result['metadata']['ko'], 4460)
        self.assertIn('Kursdaten fehlen', result['reason'])


if __name__ == '__main__':
    unittest.main()
