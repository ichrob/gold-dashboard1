import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import comparison_store as store
import future_comparison as c
import future_estimate as f

NOW = datetime(2026, 10, 5, 10, tzinfo=timezone.utc)


class ComparisonTests(unittest.TestCase):
    def inputs(self):
        ref = NOW-timedelta(seconds=600)
        research = dict(contract='GCZ26', underlyingAt=ref.isoformat(), underlyingPriceUsd=4200)
        spots = [dict(at=(ref+timedelta(seconds=i)).isoformat(), price=4100+i*.01,
                      contract='GCZ26', proxyKind='gold-api-spot') for i in range(0, 601, 20)]
        cfds = [dict(at=(ref+timedelta(seconds=i)).isoformat(), price=4180+i*.02,
                     contract='GCZ26', proxyKind='investing-cfd') for i in range(0, 601, 20)]
        return research, spots, cfds

    def test_common_anchor_and_time_with_distinct_formulas(self):
        research, spots, cfds = self.inputs()
        p, interpolated = c.predict(research, spots, cfds, NOW)
        self.assertEqual(p['at'], NOW.isoformat())
        self.assertEqual(p['spot'], round(4200*4106/4100, 2))
        self.assertEqual(p['cfd'], 4212)
        self.assertFalse(interpolated)

    def test_aligns_interleaved_observations_without_inventing_timestamps(self):
        research, spots, cfds = self.inputs()
        for row in cfds:row['at']=(f.stamp(row['at'])+timedelta(seconds=10)).isoformat()
        research['underlyingAt']=(NOW-timedelta(seconds=580)).isoformat()
        p, interpolated = c.predict(research, spots, cfds, NOW+timedelta(seconds=10))
        self.assertTrue(interpolated)
        self.assertEqual(p['at'], NOW.isoformat())

    def test_missing_stale_gap_and_wrong_contract_rejected(self):
        research, spots, cfds = self.inputs()
        for r, s, d, now in [(research, spots, [], NOW), (research, spots, cfds, NOW+timedelta(seconds=61)),
                              (research, spots, cfds[:3]+cfds[-2:], NOW),
                              ({**research, 'contract':'GC=F'}, spots, cfds, NOW)]:
            with self.assertRaises(ValueError):c.predict(r, s, d, now)

    def test_study_cannot_feed_active_cfd_selection(self):
        research, spots, cfds = self.inputs()
        with patch.object(f, '_ticks', []), patch.object(f, '_spot_ticks', spots), \
             patch.object(f, '_research_reference', research), patch.object(c, '_ticks', cfds), \
             patch.object(f.estimate_quality, 'record'), patch.object(f.estimate_quality, 'observe'):
            result = f.current_estimate(research, NOW)
        self.assertEqual(result['proxyKind'], 'gold-api-spot')

    def test_summary_uses_identical_pairs_and_reports_worst_errors(self):
        rows = [(NOW-timedelta(seconds=60*i), NOW-timedelta(seconds=60*i+600), '301–900s',
                 4202, 4201, 4200, NOW-timedelta(seconds=60*i), NOW) for i in range(20)]
        s = store.summarize(rows, NOW)
        self.assertEqual(s['spot']['mae'], 2)
        self.assertEqual(s['cfd']['maximum'], 1)
        self.assertTrue(s['preliminaryReady'])
        self.assertEqual(s['lowerMeanError'], 'cfd')
        self.assertFalse(store.summarize(rows[:1], NOW)['preliminaryReady'])
        self.assertFalse(store.summarize(rows, NOW+timedelta(hours=1))['preliminaryReady'])

    def test_event_validation(self):
        research, spots, cfds = self.inputs()
        p, _ = c.predict(research, spots, cfds, NOW)
        store.checked(p, NOW)
        for changes in [dict(spot=True), dict(cfd=float('nan')), dict(at=NOW.replace(tzinfo=None).isoformat()),
                        dict(referenceAt=(NOW+timedelta(seconds=1)).isoformat())]:
            with self.assertRaises(ValueError):store.checked({**p, **changes}, NOW)

    def test_paused_worker_does_not_fetch_market_sources(self):
        with patch.object(c, '_report', {}), patch.object(c.investing_card, 'fetch') as fetch, \
             patch.object(c.bob_validation_store, 'request', return_value=dict(summary={}, predictionCount=0, truthCount=0)):
            c.tick(NOW.replace(hour=22))
            self.assertEqual(c.status()['state'], 'paused')
            fetch.assert_not_called()


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'])
        schema = 'comparison_test_'+uuid.uuid4().hex
        self.conn.execute('CREATE SCHEMA '+schema)
        self.conn.execute('SET search_path TO '+schema)
        store.init(self.conn)
        now = datetime.now(timezone.utc)
        self.at = (now-timedelta(seconds=30)).isoformat()
        self.pred = dict(type='prediction', at=self.at, referenceAt=(now-timedelta(seconds=630)).isoformat(), spot=4202, cfd=4201)
        self.truth = dict(type='truth', at=self.at, value=4200)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def write(self, *events):return store.handle(self.conn, 'write', dict(events=list(events)))

    def test_frozen_pair_survives_repeated_reads_without_double_counting(self):
        self.write(self.pred)
        result = self.write(self.truth)
        self.assertEqual(result['summary']['count'], 1)
        self.assertEqual(result['summary']['spot']['mae'], 2)
        self.write({**self.pred, 'spot':9999})
        result = self.write(self.truth)
        self.assertEqual(result['summary']['spot']['mae'], 2)
        self.assertEqual(result['summary']['count'], 1)

    def test_known_truth_cannot_validate_later_prediction(self):
        self.write(self.truth)
        self.write(self.pred)
        self.assertEqual(self.write(self.truth)['summary']['count'], 0)

    def test_same_batch_truth_not_used_for_backfilled_prediction(self):
        self.assertEqual(self.write(self.pred, self.truth)['summary']['count'], 0)

    def test_wrong_time_is_not_matched_and_conflicting_truth_rejected(self):
        self.write(self.pred)
        later = (store.stamp(self.at)+timedelta(seconds=6)).isoformat()
        self.assertEqual(self.write({**self.truth, 'at':later})['summary']['count'], 0)
        with self.assertRaises(ValueError):self.write({**self.truth, 'at':later, 'value':4000})


if __name__ == '__main__':unittest.main()
