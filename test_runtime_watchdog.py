import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import runtime_watchdog as w

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
SHA = 'a'*40


class RuntimeWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(w._report), w._release_attempt
        w._report.clear()
        w._release_attempt = None

    def tearDown(self):
        w._report.clear()
        w._report.update(self.saved[0])
        w._release_attempt = self.saved[1]

    def health(self, url):
        if url.endswith('/health/background'):
            return {'status':'ok'}
        if url.startswith(w.watchdog.PUSH):
            return {'ok':True, 'build':SHA, 'productAuditCodes':['product-ko-validity-missing']}
        return {'status':'ok', 'build':SHA}

    def ci(self):
        return SHA, [dict(head_sha=SHA, name='Bob CI', event='push', status='completed',
                          conclusion='success', updated_at=(NOW-timedelta(minutes=2)).isoformat())]

    def test_health_and_exact_release_work_without_github_schedule(self):
        w.tick(NOW, 0, self.health, self.ci)
        r = w.snapshot(NOW.timestamp())
        self.assertEqual(r['health']['state'], 'ok')
        self.assertEqual(r['deployment']['state'], 'verified')
        self.assertTrue(r['independentOfGitHubSchedule'])
        self.assertNotIn('product-ko-validity-missing', str(r))

    def test_github_failure_never_erases_health_or_causes_fast_retries(self):
        with patch.object(w.release, 'read_ci_evidence', side_effect=OSError('private error')) as ci:
            for n in range(7):
                w.tick(NOW+timedelta(seconds=300*n), 300*n, self.health, ci)
        self.assertEqual(ci.call_count, 2)
        r = w.snapshot((NOW+timedelta(minutes=30)).timestamp())
        self.assertEqual(r['health']['state'], 'ok')
        self.assertEqual(r['deployment']['state'], 'unavailable')
        self.assertNotIn('private error', str(r))

    def test_timeout_is_not_a_success_and_stale_success_is_not_current(self):
        def unavailable(url):raise TimeoutError('private URL')
        w.tick(NOW, 0, unavailable, self.ci)
        r = w.snapshot(NOW.timestamp())
        self.assertEqual(r['health']['state'], 'degraded')
        self.assertIn('scanner-unreachable', r['health']['codes'])
        self.assertNotEqual(r['deployment']['state'], 'verified')
        w.tick(NOW, 300, self.health, self.ci)
        r = w.snapshot((NOW+timedelta(minutes=8)).timestamp())
        self.assertEqual(r['health']['state'], 'stale')
        self.assertFalse(r['health']['fresh'])
        self.assertNotIn('private URL', str(r))

    def test_observations_are_bounded_and_snapshots_are_detached(self):
        for n in range(20):w.tick(NOW, n*300, self.health, self.ci)
        r = w.snapshot(NOW.timestamp())
        self.assertEqual(len(r['samples']), 12)
        r['health']['state'] = 'mutated'
        self.assertEqual(w.snapshot(NOW.timestamp())['health']['state'], 'ok')

    def test_start_is_idempotent_and_does_not_start_on_import(self):
        with patch.object(w, '_thread', None), patch.object(w.threading, 'Thread') as thread:
            thread.return_value.is_alive.return_value = True
            w.start(); w.start()
            self.assertEqual(thread.call_count, 1)
            thread.return_value.start.assert_called_once()


if __name__ == '__main__':unittest.main()
