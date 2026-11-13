import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import signal_freshness as freshness

NOW = 1793862000


def areas(age=10, session='trading'):
    return {'market': {'sessionMode': session, 'source': {
        'spot_price_as_of': datetime.fromtimestamp(NOW-age, timezone.utc).isoformat()}},
        'analysis': {'timeframes': {'15m': {'result': {
            'dataAt': (NOW-age)*1000, 'analysisCompletedAt': (NOW-age+1)*1000}}}},
        'background': {'lastSuccessAt': NOW-age, 'expectedCycleSeconds': 30}}


class FreshnessTests(unittest.TestCase):
    def test_ages_and_thresholds(self):
        for age, status in ((10, 'observed'), (60, 'observed'), (61, 'degraded'),
                            (120, 'degraded'), (121, 'stale')):
            report = freshness.snapshot(areas(age), NOW)
            self.assertEqual(report['status'], status)
            self.assertEqual(report['analysis']['15m']['input']['ageSeconds'], age)

    def test_new_cache_cannot_hide_old_source_or_analysis(self):
        data = areas(200)
        data['market'].update(status='observed', cachedAt=NOW)
        data['analysis']['timeframes']['15m']['result']['priceFresh'] = True
        before = copy.deepcopy(data)
        self.assertEqual(freshness.snapshot(data, NOW)['status'], 'stale')
        self.assertEqual(data, before)

    def test_night_cadence_does_not_mask_active_trade_or_rewrite_age(self):
        data = areas(200, 'night')
        data['background']['expectedCycleSeconds'] = 300
        report = freshness.snapshot(data, NOW)
        self.assertEqual(report['status'], 'observed')
        self.assertFalse(report['timelinessExpected'])
        self.assertFalse(report['marketSource']['within60Seconds'])
        self.assertEqual(report['marketSource']['ageSeconds'], 200)
        data['background']['expectedCycleSeconds'] = 30
        self.assertEqual(freshness.snapshot(data, NOW)['status'], 'stale')

    def test_invalid_or_future_clocks_never_pass(self):
        for value in (None, True, float('nan'), float('inf'), (NOW+1)*1000):
            data = areas()
            data['analysis']['timeframes']['15m']['result']['dataAt'] = value
            self.assertEqual(freshness.snapshot(data, NOW)['status'], 'unavailable')
        for value in (None, 'invalid', '2026-11-05T09:00:00'):
            data = areas()
            data['market']['source']['spot_price_as_of'] = value
            self.assertEqual(freshness.snapshot(data, NOW)['status'], 'unavailable')
        self.assertEqual(freshness.snapshot({}, NOW)['status'], 'unavailable')

    def test_bounded_receipts_exclude_tests_and_preserve_missing(self):
        data = areas()
        def record(delay, **kw):
            return dict(test=False, synthetic=False, outcome='provider-accepted',
                        latency={'sourceToBrowserReceiptMs': delay}, **kw)
        test = record(999999)
        test['test'] = True
        data['pushDeliveries'] = {'records': [record(14000), record(61000), record(None),
                                             test, record(-1), record(True)]}
        sample = freshness.snapshot(data, NOW)['pushSample']
        self.assertEqual(sample['timedBrowserReceipts'], 2)
        self.assertEqual(sample['missingTiming'], 3)
        self.assertEqual(sample['maxSeconds'], 61)
        self.assertEqual(sample['over60Seconds'], 1)

    def test_existing_diagnostics_expose_control_in_all_relevant_views(self):
        import bob_diagnostics as diagnostics
        with patch.object(freshness.time, 'time', return_value=NOW):
            report = diagnostics.collect({key: lambda value=value: value
                                          for key, value in areas().items()})
        for focus in ('sources', 'signals', 'repairs'):
            self.assertIn('signalFreshness', diagnostics.focused_report(report, focus)['areas'])


if __name__ == '__main__':
    unittest.main()
