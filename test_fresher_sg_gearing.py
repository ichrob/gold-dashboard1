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
