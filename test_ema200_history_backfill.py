"""EMA200 warmup from dated historical XAU/USD candles; no change to entry gates."""
import time
import unittest
from unittest.mock import patch

import server

HOUR_MS = 3600000


def candle_series(count, *, step=HOUR_MS, value=4300):
    # The most recent candle is fully closed in the present source hour.
    now_ms = int(time.time() * 1000)
    last = now_ms // step * step - step
    return [dict(openTime=last - (count - i - 1) * step,
                 open=value + i * 0.03, high=value + i * 0.03 + 1,
                 low=value + i * 0.03 - 1, close=value + i * 0.03 + 0.2,
                 isOpen=False, instrument='XAU/USD',
                 source='test provider') for i in range(count)]


def xaus_points(rows):
    return [dict(t=row['openTime'] // 1000, o=row['open'], h=row['high'],
                 l=row['low'], c=row['close']) for row in rows]


class EMA200HistoryWarmupTests(unittest.TestCase):
    def setUp(self):
        server._ema_backfill_attempted.clear()
        server._ema_backfill_series.clear()
        server._technical_history.clear()

    def test_fresh_170_hours_fetches_full_240_hours_without_splicing(self):
        short = candle_series(170)
        full = candle_series(240, value=4320)
        with patch.object(server.technical_candles, 'fetch', return_value=short), \
             patch.object(server, 'fetch_json', return_value={'points': xaus_points(full)}) as provider:
            result = server.fetch_technical_history('1h', '3mo')
            second = server.fetch_technical_history('1h', '3mo')
        self.assertEqual(len(result), 240)
        self.assertEqual(result[0]['close'], full[0]['close'])
        self.assertEqual([b['source'] for b in result], ['XAUS · datierte XAU/USD-Historie'] * 240)
        self.assertTrue(server._ema_history_sufficient(result, 60))
        self.assertEqual(server._ema([b['close'] for b in result], 200),
                         server._ema([b['close'] for b in second], 200))
        self.assertEqual(provider.call_count, 1, 'The alternate must be rate-limited')
        self.assertEqual(len(second), 240)

    def test_fresh_195_fifteen_minute_bars_backfill_without_mixing_sources(self):
        step = 900000
        original = candle_series(195, step=step)
        longer = candle_series(222, step=step, value=4270)
        with patch.object(server.technical_candles, 'fetch', return_value=original), \
             patch.object(server, 'fetch_json', return_value={'points': xaus_points(longer)}) as provider:
            result = server.fetch_technical_history('15m', '5d')
        self.assertEqual(len(result), 222)
        self.assertEqual(result[0]['open'], longer[0]['open'])
        self.assertTrue(server._ema_history_sufficient(result, 15))
        provider.assert_called_once()

    def test_short_history_does_not_block_ema20_ema50_signals(self):
        short = candle_series(170)
        self.assertFalse(server._ema_history_sufficient(short, 60))
        checked = server._mtf_score(short, '1h')
        self.assertTrue(checked['available'])
        self.assertTrue(checked['fresh'])
        self.assertEqual(checked['bars'], 170)

    def test_unavailable_or_short_fallback_leaves_valid_original(self):
        short = candle_series(170)
        with patch.object(server.technical_candles, 'fetch', return_value=short), \
             patch.object(server, 'fetch_json', return_value={'points': xaus_points(candle_series(180))}):
            r = server.fetch_technical_history('1h', '3mo')
        self.assertEqual(len(r), 170)
        self.assertFalse(server._ema_history_sufficient(r, 60))
        self.assertFalse(server._ema_backfill_series)
        with patch.object(server.technical_candles, 'fetch', return_value=short), \
             patch.object(server, 'fetch_json', side_effect=OSError('provider unavailable')):
            server._ema_backfill_attempted.clear()
            r = server.fetch_technical_history('1h', '3mo')
        self.assertEqual(len(r), 170)

    def test_rejects_other_instrument_or_old_last_source_clock(self):
        short = candle_series(170)
        wrong = candle_series(220)
        for b in wrong:
            b['instrument'] = 'GC=F'
        self.assertFalse(server._ema_history_sufficient(wrong, 60))
        older = candle_series(220)
        for b in older:
            b['openTime'] -= HOUR_MS * 8
        self.assertFalse(server._ema_history_sufficient(older, 60))
        with patch.object(server.technical_candles, 'fetch', return_value=short), \
             patch.object(server, 'normalize_chart_points', return_value=wrong), \
             patch.object(server, 'fetch_json', return_value={'points': xaus_points(wrong)}):
            r = server.fetch_technical_history('1h', '3mo')
        self.assertEqual(len(r), 170)

    def test_current_partial_hour_is_not_a_completed_ema_candle(self):
        rows = candle_series(200)
        rows[-1]['isOpen'] = True
        self.assertFalse(server._ema_history_sufficient(rows, 60))
        bad = candle_series(201)
        bad[-1]['openTime'] = int(time.time() * 1000) // HOUR_MS * HOUR_MS
        server.mark_bar_state(bad, 60)
        self.assertFalse(server._ema_history_sufficient(bad, 60))

    def test_200_full_current_provider_does_not_request_fallback(self):
        full = candle_series(220)
        with patch.object(server.technical_candles, 'fetch', return_value=full), \
             patch.object(server, 'fetch_json') as provider:
            r = server.fetch_technical_history('1h', '3mo')
        self.assertEqual(r, full)
        provider.assert_not_called()

    def test_native_half_hour_warmup_is_retained_for_deadline_fallback(self):
        full=candle_series(600,step=1800000)
        with patch.object(server.technical_candles,'fetch',return_value=[]),patch.object(server,'fetch_json',return_value={'points':xaus_points(full)}) as fetch:
            result=server.fetch_technical_history('30m','1mo')
        self.assertEqual(len(result),600)
        self.assertEqual(server.retain_technical_history('30m',[]),result)
        self.assertIn('interval=30m',fetch.call_args.args[0])

    def test_four_hour_warmup_from_complete_hourly_candles(self):
        full=candle_series(1200)
        with patch.object(server.technical_candles,'fetch',return_value=candle_series(180,step=14400000)),patch.object(server,'fetch_json',return_value={'points':xaus_points(full)}) as fetch:
            result=server.fetch_technical_history('4h','3mo')
        self.assertGreaterEqual(len(result),299)
        self.assertTrue(server._ema_history_sufficient(result,240))
        self.assertIn('interval=1h',fetch.call_args.args[0])

    def test_stale_minute_fallback_retries_after_30s_not_five_minutes(self):
        now = time.time()
        stale = candle_series(220, step=60000)
        for row in stale:
            row['openTime'] -= 600000
        with patch.object(server.time, 'time', return_value=now), \
             patch.object(server, 'fetch_json', return_value={'points': []}) as fetch:
            self.assertEqual(server._ema200_history_backfill('1m', '5d', stale), stale)
            with patch.object(server.time, 'time', return_value=now+29):
                server._ema200_history_backfill('1m', '5d', stale)
            self.assertEqual(fetch.call_count, 1)
            with patch.object(server.time, 'time', return_value=now+30):
                result = server._ema200_history_backfill('1m', '5d', stale)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(result, stale)
            self.assertFalse(server.technical_history_fresh(result, 1, now+30))

    def test_confirmed_prefix_survives_shorter_same_source_window(self):
        full=candle_series(300)
        server.retain_technical_history('1h',full)
        self.assertEqual(len(server.retain_technical_history('1h',full[-50:])),300)
        other=[dict(b,source='other') for b in full[-50:]]
        self.assertEqual(len(server.retain_technical_history('1h',other)),50)


if __name__ == '__main__':
    unittest.main()
