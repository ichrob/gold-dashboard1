import unittest
from datetime import datetime, timezone

from storage_prevention import assess
from storage_capacity import ALLOCATION_BYTES

NOW = datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc).timestamp()


class StoragePreventionTests(unittest.TestCase):
    def test_physical_thresholds_are_read_only_not_writer_permissions(self):
        for pct, severity in [(21, 'normal'), (50, 'caution'),
                              (70, 'action'), (80, 'high'), (90, 'emergency')]:
            with self.subTest(percent=pct):
                result = assess(physical_bytes=ALLOCATION_BYTES * pct//100,
                                physical_observed_at=NOW-20,
                                database_bytes=950_000_000, now=NOW)
                self.assertEqual(result['severity'], severity)
                self.assertEqual(result['physicalUsedPct'], pct)
                self.assertIsNone(result['diskBytesFreed'])
                self.assertFalse(result['automaticArchiveTriggered'])
                self.assertFalse(result['deletionAuthorized'])
                self.assertFalse(result['retentionChanged'])

    def test_missing_or_stale_physical_measurement_cannot_be_green(self):
        for value, at in [(None, NOW), (True, NOW), (-1, NOW),
                          (1_000_000_000, NOW-301),
                          (1_000_000_000, NOW+1),
                          (1_000_000_000, 'bad')]:
            with self.subTest(value=value, at=at):
                result=assess(physical_bytes=value,
                              physical_observed_at=at, now=NOW)
                self.assertEqual(result['severity'], 'unknown')
                self.assertEqual(result['status'], 'physical-measurement-unavailable')

    def test_growth_is_labeled_logical_and_never_provider_bytes(self):
        history = [
            {'status': 'observed', 'startSlot': 1, 'dbDelta': 52_000_000},
            {'status': 'observed', 'startSlot': 2, 'dbDelta': 48_000_000},
            {'status': 'observed', 'startSlot': 3, 'dbDelta': -8_000_000},
            {'status': 'observed', 'startSlot': 4, 'dbDelta': 999_999_999},
            {'status': 'observed', 'startSlot': 5, 'dbDelta': 999_999_999},
        ]
        result=assess(physical_bytes=1_000_000_000,
                      physical_observed_at=NOW-5, daily=history, now=NOW)
        self.assertEqual(result['logicalGrowthState'], 'rapid-logical-growth')
        self.assertEqual(result['logicalDailySampleCount'], 4)
        self.assertEqual(result['maxObservedLogicalDailyIncreaseBytes'], 999_999_999)
        self.assertEqual(result['severity'], 'normal')
        self.assertIsNone(result['diskBytesFreed'])
        unchanged=assess(daily=[history[0], history[0]],now=NOW)
        self.assertEqual(unchanged['logicalGrowthState'], 'insufficient')

    def test_journal_cap_is_only_an_estimate_no_deletion(self):
        result=assess(diagnostic_live_estimate=86_000,now=NOW)
        self.assertEqual(result['diagnosticJournalCapState'],
                         'estimated-over-approved-cap')
        self.assertFalse(result['deletionAuthorized'])
        self.assertEqual(assess(diagnostic_live_estimate=None,
                                now=NOW)['diagnosticJournalCapState'], None)

    def test_archive_age_and_drive_quota_are_historical_only(self):
        at=datetime.fromtimestamp(NOW-60*60,timezone.utc).isoformat()
        fresh=assess(now=NOW,archive_verified_at=at,
                     drive_quota_available=4_000_000_000)
        self.assertEqual(fresh['lastVerifiedArchiveProofState'],'fresh')
        self.assertEqual(fresh['lastArchiveQuotaAvailableBytes'],4_000_000_000)
        self.assertFalse(fresh['archiveQuotaIsCurrent'])
        stale=assess(now=NOW,archive_verified_at=datetime.fromtimestamp(
            NOW-8*3600,timezone.utc).isoformat(),drive_quota_available=True)
        self.assertEqual(stale['lastVerifiedArchiveProofState'],'stale')
        self.assertIsNone(stale['lastArchiveQuotaAvailableBytes'])


if __name__ == '__main__':
    unittest.main()
