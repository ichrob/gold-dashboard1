import unittest
from datetime import datetime, timezone

from chart_session_display import historical_chart, candle_tap_details


def bar(iso, close, **extra):
    ts = int(datetime.fromisoformat(iso).timestamp() * 1000)
    return dict(openTime=ts, open=close, high=close, low=close, close=close,
                source="biquote", instrument="XAU/USD", **extra)


class ChartSessionDisplayTests(unittest.TestCase):
    def test_friday_retained_during_weekend(self):
        friday = [bar("2026-11-13T19:00:00+00:00", 4000),
                  bar("2026-11-13T19:05:00+00:00", 4001)]
        self.assertEqual(historical_chart(friday, closed_session=True)["bars"], friday)
        self.assertEqual(historical_chart(friday, closed_session=True)["lastConfirmedClose"], 4001)

    def test_no_synthetic_weekend_bars(self):
        bars = [bar("2026-11-13T19:05:00+00:00", 4001),
                bar("2026-11-14T12:00:00+00:00", 4001, synthetic=True)]
        self.assertEqual(len(historical_chart(bars, closed_session=True)["bars"]), 1)

    def test_real_sunday_reopening_not_removed_by_weekday(self):
        bars = [bar("2026-11-13T19:05:00+00:00", 4001),
                bar("2026-11-15T23:00:00+00:00", 4002)]
        self.assertEqual(len(historical_chart(bars)["bars"]), 2)

    def test_open_bar_excluded_and_original_untouched(self):
        rows = [bar("2026-11-13T19:00:00+00:00", 4000),
                bar("2026-11-13T19:05:00+00:00", 4001, isOpen=True)]
        self.assertEqual(len(historical_chart(rows)["bars"]), 1)
        self.assertEqual(len(rows), 2)

    def test_tap_zurich_time_and_exact_close(self):
        info = candle_tap_details(bar("2026-11-13T19:05:00+00:00", 4001.25))
        self.assertEqual(info["timeZurich"], "2026-11-13T20:05:00+01:00")
        self.assertEqual(info["close"], 4001.25)

    def test_empty_history(self):
        self.assertEqual(historical_chart([], closed_session=True)["status"], "no-confirmed-candles")


if __name__ == "__main__":
    unittest.main()
