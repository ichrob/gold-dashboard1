import unittest
import candle_reliability as c
from source_availability import windows


class AvailabilityTests(unittest.TestCase):
    def test_observed_percentage_excludes_pauses_and_unknown(self):
        row = c.transition(None, 'current', 3600)
        row = c.transition(row, 'stale', 3660)
        row = c.transition(row, 'paused', 3690)
        row = c.transition(row, 'current', 3720)
        row = c.transition(row, 'current', 4000)  # Restart gap is unknown.
        w = windows(row, 7200)['24h']
        self.assertEqual(w['availabilityPct'], 66.67)
        self.assertEqual(w['currentSeconds'], 60)
        self.assertEqual(w['badSeconds'], 30)
        self.assertEqual(w['pausedSeconds'], 30)
        self.assertEqual(w['unknownSeconds'], 86400 - 120)
        self.assertLess(w['coveragePct'], 1)

    def test_cross_hour_and_duplicate_or_reverse_clock(self):
        row = c.transition(None, 'current', 3580)
        row = c.transition(row, 'stale', 3620)
        self.assertEqual(row['availabilityHours'], {'0': [20, 0, 0], '1': [20, 0, 0]})
        self.assertEqual(c.transition(row, 'current', 3620), row)
        self.assertEqual(c.transition(row, 'current', 3500), row)
        self.assertEqual(windows(row, 3600)['24h']['currentSeconds'], 20)

    def test_migration_does_not_invent_historical_uptime(self):
        old = dict(state='current', checkedAt=100, incidents=0, badSeconds=10,
                   unknownSeconds=0, events=[], since=1)
        row = c.transition(old, 'current', 130)
        self.assertEqual(windows(row, 3600)['7d']['currentSeconds'], 30)
        self.assertIsNone(windows({}, 3600)['24h']['availabilityPct'])

    def test_retention_bounded_and_large_gap_not_looped(self):
        row = c.transition(None, 'current', 1)
        row = c.transition(row, 'current', 31)
        row = c.transition(row, 'current', 10000000)
        self.assertEqual(row['availabilityHours'], {})


if __name__ == '__main__':
    unittest.main()
