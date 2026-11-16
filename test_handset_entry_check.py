import copy
import unittest
from datetime import datetime, timezone
from handset_entry_check import assess

NOW = 1794834000000


def stamp(delta):
    return datetime.fromtimestamp((NOW+delta)/1000, timezone.utc).isoformat()


class EntryCheck(unittest.TestCase):
    def setUp(self):
        self.row = dict(available=True, entrySuitable=True, reasons=[],
                        modelReferenceAt=stamp(-60000), observedAt=stamp(-30000))

    def test_current_capture_still_does_not_establish_broker_time(self):
        before = copy.deepcopy(self.row)
        answer = assess(self.row, NOW)
        self.assertEqual(answer['code'], 'BROKER_SOURCE_TIME_UNVERIFIED')
        for flag in ('readRequired', 'readDispatched', 'entryApproved',
                     'brokerExecutionVerified', 'realOrders'):
            self.assertIs(answer[flag], False)
        self.assertEqual(self.row, before)

    def test_old_missing_future_and_pre_reference_capture_need_new_read(self):
        for captured in (None, 'bad', '2026-11-16T13:00:00',
                         stamp(-90001), stamp(-60001), stamp(1)):
            with self.subTest(captured=captured):
                answer = assess(dict(self.row, observedAt=captured), NOW)
                self.assertEqual(answer['code'], 'NEW_DEGIRO_READ_REQUIRED')
                self.assertTrue(answer['readRequired'])
                self.assertFalse(answer['readDispatched'])

    def test_missing_stale_future_and_naive_model_reference_block(self):
        for value in (None, 'bad', stamp(-90001), stamp(1),
                      '2026-11-16T13:00:00'):
            self.assertEqual(assess(dict(self.row, modelReferenceAt=value), NOW)['code'],
                             'MODEL_REFERENCE_NOT_FRESH')

    def test_only_explicit_signal_and_usable_comparison_request_read(self):
        for signal in (None, False, 1, 'true'):
            answer = assess(dict(self.row, entrySuitable=signal), NOW)
            self.assertEqual(answer['code'], 'WAITING_FOR_SIGNAL')
            self.assertFalse(answer['readRequired'])
        for change in (dict(available=False), dict(available=1), dict(reasons=['budget'])):
            self.assertEqual(assess(dict(self.row, **change), NOW)['code'], 'COMPARISON_BLOCKED')

    def test_recalculation_cannot_refresh_original_capture(self):
        self.row['observedAt'] = stamp(-120000)
        self.row['calculatedAt'] = NOW
        self.row['historicalOnly'] = False
        self.assertEqual(assess(self.row, NOW)['code'], 'NEW_DEGIRO_READ_REQUIRED')

    def test_invalid_assessment_clock_rejected(self):
        for value in (True, None, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                assess(self.row, value)
