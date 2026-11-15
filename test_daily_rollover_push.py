"""Regression tests for #1642: silent, source-corroborated daily gold rollover."""
import json
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import background_push as b


ZURICH = ZoneInfo('Europe/Zurich')


def at(year, month, day, hour, minute=0, second=0):
    return int(datetime(year, month, day, hour, minute, second, tzinfo=ZURICH).timestamp() * 1000)


def kinds(events):
    return [event['data']['eventKind'] for event in events]


class DailyGoldRolloverPushTests(unittest.TestCase):
    def setUp(self):
        self.settings = {'trade': None}
        self.bar = at(2026, 11, 12, 22, 45)
        self.market = {'ready': True, 'priceFresh': True, 'price': 105,
                       'analysisBarAt': self.bar, 'direction': 'NEUTRAL',
                       'mtf': 'NEUTRAL', 'atr': 4,
                       'session': {'entryAllowed': False}}

    def advance(self, state, when, market=None, *, trade=False, settings=None):
        inputs = self.market if market is None else market
        return b.advance(state, self.settings if settings is None else settings,
                         inputs, True, trade, now=when, log=False)

    def test_rollover_clock_is_new_york_based_and_dst_safe(self):
        # Europe/US clocks change on different dates; never hardcode 23:00 Zurich.
        for year, month, day, hour, close_hour in (
                (2026, 3, 18, 22, 22), (2026, 10, 29, 22, 22),
                (2026, 11, 12, 23, 23)):
            with self.subTest(month=month, day=day):
                now = at(year, month, day, hour, 25)
                bar = at(year, month, day, close_hour - 1, 45)
                self.assertTrue(b.daily_gold_rollover_pause(now, bar, now - 19000))
                self.assertFalse(b.daily_gold_rollover_pause(now + 3600000, bar, now + 3600000))
        # Friday is weekend-close territory, not the Mon–Thu daily rollover.
        self.assertFalse(b.daily_gold_rollover_pause(
            at(2026, 11, 13, 23, 25), at(2026, 11, 13, 22, 45),
            at(2026, 11, 13, 23, 24, 41)))

    def test_reported_2325_data_push_is_silent_but_clocks_remain_original(self):
        preclose = at(2026, 11, 12, 22, 59, 30)
        state, _ = self.advance({}, preclose, {**self.market, 'dataAt': preclose})
        now = at(2026, 11, 12, 23, 25)
        source_at = at(2026, 11, 12, 23, 24, 41)
        stale = {**self.market, 'ready': False, 'dataAt': source_at}
        state, events = self.advance(state, now, stale)
        self.assertNotIn('data-unavailable', kinds(events))
        self.assertEqual(state['dataStatus'], 'rollover')
        self.assertFalse(state['healthy'])
        self.assertFalse(state['continuedCalculation']['marketClosed'])
        self.assertTrue(state['continuedCalculation']['stale'])
        self.assertEqual(state['continuedCalculation']['dataAt'], source_at)
        self.assertTrue(any(x['kind'] == 'data-rollover' and x['outcome'] == 'suppressed'
                            for x in state['pushHistory']))
        # A persisted state resumes normally without inventing a fresh analysis.
        restored = json.loads(json.dumps(state))
        later = at(2026, 11, 12, 23, 30)
        restored, events = self.advance(restored, later, {
            **stale, 'dataAt': at(2026, 11, 12, 23, 29, 41)})
        self.assertEqual(restored['dataStatus'], 'rollover')
        self.assertNotIn('data-unavailable', kinds(events))

    def test_after_reopen_real_outage_alerts_after_debounce(self):
        now = at(2026, 11, 12, 23, 25)
        fresh = {**self.market, 'ready': False,
                 'dataAt': at(2026, 11, 12, 23, 24, 41)}
        state, _ = self.advance({}, now, fresh)
        self.assertEqual(state['dataStatus'], 'rollover')
        midnight = at(2026, 11, 13, 0, 0, 1)
        outage = {**fresh, 'priceFresh': False}
        for offset, expected in ((0, False), (30000, False), (60000, True)):
            state, events = self.advance(state, midnight + offset, outage)
            self.assertEqual('data-unavailable' in kinds(events), expected)
        self.assertEqual(state['dataStatus'], 'unavailable')

    def test_preexisting_outage_is_not_hidden_by_rollover(self):
        start = at(2026, 11, 12, 22, 40)
        failed = {**self.market, 'ready': False, 'dataAt': start,
                  'analysisBarAt': at(2026, 11, 12, 22, 35)}
        state, _ = self.advance({}, start, failed)
        state, _ = self.advance(state, start + 30000, failed)
        state, events = self.advance(state, start + 60000, failed)
        self.assertIn('data-unavailable', kinds(events))
        midnight_gap = {**failed, 'analysisBarAt': self.bar,
                        'dataAt': at(2026, 11, 12, 23, 24, 41)}
        state, events = self.advance(state, at(2026, 11, 12, 23, 25), midnight_gap)
        self.assertNotEqual(state['dataStatus'], 'rollover')
        self.assertFalse(state['announcedHealthy'])

    def test_no_suppression_without_independent_fresh_spot_or_close_bar(self):
        now = at(2026, 11, 12, 23, 25)
        spot = at(2026, 11, 12, 23, 24, 41)
        self.assertFalse(b.daily_gold_rollover_pause(now, None, spot))
        self.assertFalse(b.daily_gold_rollover_pause(now, self.bar - 1800000, spot))
        self.assertFalse(b.daily_gold_rollover_pause(now, self.bar, spot - 180000))
        for change in ({'analysisError': True}, {'priceFresh': False},
                       {'analysisBarAt': None}):
            with self.subTest(change=change):
                failed = {**self.market, 'ready': False, 'dataAt': spot, **change}
                state, _ = self.advance({}, now, failed)
                state, _ = self.advance(state, now + 30000, failed)
                state, events = self.advance(state, now + 60000, failed)
                self.assertIn('data-unavailable', kinds(events))
                self.assertNotEqual(state['dataStatus'], 'rollover')

    def test_active_trade_alerts_are_not_muted_at_rollover(self):
        now = at(2026, 11, 12, 23, 25)
        settings = b.config({'trade': {
            'active': True, 'tradeId': 'rollover-test', 'instrument': 'XAU/USD',
            'dir': 'LONG', 'entry': 100, 'stop': 90,
            'initialRisk': 10, 'target': 150}})
        market = {**self.market, 'ready': False, 'price': 89,
                  'dataAt': at(2026, 11, 12, 23, 24, 41)}
        state, events = self.advance({}, now, market, trade=True, settings=settings)
        self.assertIn('stop-hit', kinds(events))
        self.assertNotEqual(state['dataStatus'], 'rollover')
        state, _ = self.advance(state, now + 30000, market, trade=True, settings=settings)
        state, events = self.advance(state, now + 60000, market, trade=True, settings=settings)
        self.assertIn('data-unavailable', kinds(events))


if __name__ == '__main__':
    unittest.main()
