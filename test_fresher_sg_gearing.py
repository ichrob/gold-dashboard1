import copy
import unittest
from datetime import datetime, timezone
import leverage_backup as l

class FresherSGGearingTests(unittest.TestCase):
    def test_newer_chart_and_invalid_fallbacks(self):
        now = datetime(2026, 10, 7, 11, 25, tzinfo=timezone.utc)
        at = '2026-10-07T11:24:50+00:00'
        result = dict(productVerified=True, found=True,
            metadata=dict(status=1, simpleNonQuantoTurbo=True, underlyingType='SPOT', ratio=.1),
            ask=30, askAt='2026-10-07T11:24:00+00:00', currency='EUR', source='backup',
            chartEvidence=dict(bid=24, ask=25, currency='EUR', pointAt=at))
        basis = dict(underlying='XAU/USD', price=4000, at=at, source='spot')
        fx = dict(result='success', base='USD', rates=dict(EUR=.9), data_updated_at=at,
            effective_at=dict(EUR=at), source='live', sources=dict(EUR='live'), market_session='open')
        original = copy.deepcopy(result)
        evidence = l.calculate(result, basis, fx, now)
        self.assertAlmostEqual(evidence['value'], 14.4)
        self.assertEqual(evidence['inputs']['priceKind'], 'issuer-chart')
        self.assertTrue(evidence['inputsFresh'])
        self.assertEqual(result, original)
        for change in [dict(pointAt='2026-10-07T11:23:00+00:00'),
                       dict(pointAt='2026-10-07T11:25:01+00:00'),
                       dict(ask=float('inf')), dict(bid=26),
                       dict(currency='USD'), dict(pointAt='invalid')]:
            with self.subTest(change=change):
                candidate = copy.deepcopy(result)
                candidate['chartEvidence'].update(change)
                self.assertEqual(l.calculate(candidate, basis, fx, now)['inputs']['askEur'], 30)

class ConsistentProductQuoteTests(unittest.TestCase):
    def test_public_quote_and_gearing_use_same_newer_pair(self):
        from datetime import timedelta
        from unittest.mock import patch
        import product_quotes as q
        now = datetime.now(timezone.utc)
        at = (now-timedelta(seconds=15)).isoformat()
        old = (now-timedelta(seconds=150)).isoformat()
        for isin, bid, ask, chart_bid, chart_ask in [
                ('DE000FC1CHB7',6.18,6.19,5.82,5.83),
                ('DE000FG7EPT1',25.38,25.39,25.70,25.71)]:
            with self.subTest(isin=isin):
                original = dict(isin=isin, productVerified=True, found=True,
                    eligible=False, backupActive=True, currency='EUR',
                    bid=bid, ask=ask, price=ask, bidAt=old, askAt=old,
                    source='Onvista', sourceUrl='https://www.onvista.de/',
                    metadata=dict(status=1, simpleNonQuantoTurbo=True,
                        underlyingType='SPOT', ratio=.1),
                    chartEvidence=dict(bid=chart_bid, ask=chart_ask,
                        currency='EUR', pointAt=at))
                basis = dict(underlying='XAU/USD', price=4000, at=at, source='spot')
                fx = dict(result='success', base='USD', rates=dict(EUR=.9),
                    data_updated_at=at, effective_at=dict(EUR=at), source='live',
                    sources=dict(EUR='live'), market_session='open')
                with patch.object(q, '_get_quote_primary', return_value=copy.deepcopy(original)), \
                     patch('onvista_backup.apply_backup', side_effect=lambda result, isin: result), \
                     patch('spot_data.current', return_value=basis), \
                     patch('sg_quotes.market_input', return_value=fx):
                    result = q.get_quote(isin)
                self.assertEqual(result['price'],chart_ask)
                self.assertEqual(result['analysisQuote']['ask'],chart_ask)
                self.assertEqual(result['leverageCalculation']['inputs']['askEur'],chart_ask)
                self.assertEqual(result['analysisQuote']['askAt'],at)
                self.assertEqual(result['secondaryQuote']['ask'],ask)
                self.assertEqual(result['secondaryQuote']['askAt'],old)
                self.assertFalse(result['found'])
                self.assertFalse(result['eligible'])
                self.assertFalse(result['analysisQuote']['isExecutableQuote'])
                self.assertTrue(result['leverageCalculation']['inputsFresh'])
