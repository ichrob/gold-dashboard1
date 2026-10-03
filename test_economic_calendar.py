import unittest
from datetime import datetime, timezone
import economic_calendar as c


class CalendarTests(unittest.TestCase):
    def ics(self, start, title='Consumer Price Index'):
        return 'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART'+start+'\nSUMMARY:'+title+'\nEND:VEVENT\nEND:VCALENDAR'

    def test_eastern_dst_and_winter(self):
        for date, expected in [('20260309', '12:30'), ('20261102', '13:30')]:
            e = c.parse_ics(self.ics(';TZID=US-Eastern:'+date+'T083000'), 'BLS')[0]
            self.assertIn(expected, e['at'])

    def test_utc_folded_title(self):
        event = c.parse_ics(self.ics(';VALUE=DATE-TIME:20261030T123000Z', 'Personal Income and \n Outlays'), 'BEA')[0]
        self.assertIn('PCE', event['title'])
        self.assertIn('12:30', event['at'])

    def test_bad_sources_not_empty_success(self):
        for text in ['<html>blocked</html>', self.ics(':20261030T083000')]:
            with self.assertRaises(ValueError):
                c.parse_ics(text, 'BLS')

    def test_fed_cross_month_date_only(self):
        text = '2026 FOMC Meetings<div class="fomc-meeting__month"><strong>Apr/May</strong></div><div class="fomc-meeting__date">30-1*</div>'
        e = c.parse_fed(text)[0]
        self.assertEqual(e['date'], '2026-05-01')
        self.assertTrue(e['dateOnly'])
        self.assertNotIn('at', e)

    def test_failure_and_staleness_visible_without_gates(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        event = c.parse_ics(self.ics(';TZID=US-Eastern:20261005T083000'), 'BLS')
        for checked, error in [('2026-10-01T00:00:00+00:00', None), ('2026-10-03T00:00:00+00:00', 'failure')]:
            result = c.build_snapshot({'BLS': dict(events=event, checkedAt=checked, error=error)}, now)
            self.assertFalse(result['complete'])
            self.assertFalse(result['events'][0]['sourceFresh'])
            self.assertEqual(result['mode'], 'information-only')
            self.assertNotIn('blocked', result)

    def test_past_calendar_not_all_clear(self):
        now = datetime(2026, 10, 3, tzinfo=timezone.utc)
        result = c.build_snapshot({'BLS': dict(events=[], checkedAt=now.isoformat())}, now)
        self.assertFalse(result['complete'])
        self.assertEqual(result['sources'][0]['status'], 'keine kommenden Termine bestätigt')


if __name__ == '__main__':
    unittest.main()
