import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import market_session_calendar as c


class MarketCalendarTests(unittest.TestCase):
    tz = ZoneInfo('Europe/Zurich')

    def test_verified_2026_holiday_warning_is_not_an_automatic_closure(self):
        for month, day in [(1,19),(4,3),(5,25),(6,19),(9,7),(11,26),(12,25)]:
            with self.subTest(date=(month,day)):
                warning=c.advisory(datetime(2026,month,day,12,tzinfo=self.tz))
                self.assertIsNotNone(warning)
                self.assertFalse(warning['confirmedClosed'])
                self.assertIn('Sonderhandelszeiten',warning['note'])
                self.assertIn('cmegroup.com',warning['sourceUrl'])

    def test_columbus_day_is_a_venue_warning_not_gold_spot_halt(self):
        warning=c.advisory(datetime(2026,10,12,0,20,tzinfo=self.tz))
        self.assertIsNotNone(warning)
        self.assertFalse(warning['confirmedClosed'])
        self.assertIn('Columbus Day',warning['name'])
        self.assertIsNone(c.advisory(datetime(2026,10,13,0,20,tzinfo=self.tz)))

    def test_unknown_future_dates_do_not_invent_closed_markets(self):
        self.assertIsNone(c.advisory(datetime(2027,10,12,12,tzinfo=self.tz)))
        with self.assertRaises(ValueError):
            c.advisory(datetime(2026,10,12))


if __name__=='__main__': unittest.main()
