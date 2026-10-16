"""Regression: overlapping authentication reads share one DB trip, not stale state."""
import threading
import unittest
from unittest.mock import patch

import bob_auth
import bob_recovery as recovery


class RecoveryReadCoalescingTests(unittest.TestCase):
    def setUp(self):
        with recovery._STATE_READ_LOCK:
            self.assertFalse(recovery._STATE_READS)

    def test_simultaneous_mobile_requests_share_only_in_flight_state(self):
        entered = threading.Event()
        release = threading.Event()
        outcomes = []
        errors = []
        calls = []

        def read(action, user):
            calls.append((action, user))
            entered.set()
            if not release.wait(5):
                raise TimeoutError('test read not released')
            return {'passwordHash': None, 'version': 7}

        def worker():
            try:
                outcomes.append(recovery.state('account'))
            except Exception as exc:
                errors.append(type(exc).__name__)

        with patch.object(bob_auth, 'persistent_configured', return_value=True):
            with patch.object(recovery, 'rpc', side_effect=read):
                leader = threading.Thread(target=worker)
                leader.start()
                self.assertTrue(entered.wait(3))
                # Watch the existing in-flight event: don't release the
                # leader until each follower has entered the wait path.
                with recovery._STATE_READ_LOCK:
                    pending = recovery._STATE_READS['account']
                    original = pending['done']
                    waiting = threading.Condition()
                    seen = [0]

                    class ObservedEvent:
                        def wait(self, timeout=None):
                            with waiting:
                                seen[0] += 1
                                waiting.notify_all()
                            return original.wait(timeout)

                        def set(self):
                            original.set()

                    pending['done'] = ObservedEvent()
                followers = [threading.Thread(target=worker) for _ in range(16)]
                for thread in followers:
                    thread.start()
                with waiting:
                    ok = waiting.wait_for(lambda: seen[0] == len(followers), timeout=4)
                release.set()
                leader.join(5)
                for thread in followers:
                    thread.join(5)
                self.assertTrue(ok)
                self.assertFalse(leader.is_alive())
                self.assertTrue(all(not thread.is_alive() for thread in followers))
                self.assertEqual(errors, [])
                self.assertEqual(len(outcomes), 17)
                self.assertEqual(calls, [('state', 'account')])

                # A reset/revocation must be visible on the very next call;
                # there is no TTL cache, even if the earlier read succeeded.
                with patch.object(recovery, 'rpc', return_value={
                    'passwordHash': 'new-hash', 'version': 8
                }) as fresh:
                    self.assertEqual(recovery.state('account')['version'], 8)
                    fresh.assert_called_once_with('state', 'account')

    def test_failure_propagates_to_waiters_without_caching_success(self):
        entered = threading.Event()
        release = threading.Event()
        errors = []

        def unavailable(action, user):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('test read not released')
            raise OSError('database not available')

        def worker():
            try:
                recovery.state('account')
            except OSError as exc:
                errors.append(str(exc))

        with patch.object(bob_auth, 'persistent_configured', return_value=True):
            with patch.object(recovery, 'rpc', side_effect=unavailable) as rpc:
                leader = threading.Thread(target=worker)
                leader.start()
                self.assertTrue(entered.wait(3))
                with recovery._STATE_READ_LOCK:
                    pending = recovery._STATE_READS['account']
                    original = pending['done']
                    arrived = threading.Event()

                    class ObservedEvent:
                        def wait(self, timeout=None):
                            arrived.set()
                            return original.wait(timeout)

                        def set(self):
                            original.set()
                    pending['done'] = ObservedEvent()
                follower = threading.Thread(target=worker)
                follower.start()
                self.assertTrue(arrived.wait(3))
                release.set()
                leader.join(5)
                follower.join(5)
                self.assertEqual(rpc.call_count, 1)
                self.assertEqual(errors, ['database not available'] * 2)
                self.assertFalse(recovery._STATE_READS)

    def test_unconfigured_store_does_not_open_remote_request(self):
        with patch.object(bob_auth, 'persistent_configured', return_value=False):
            with patch.object(recovery, 'rpc') as rpc:
                self.assertEqual(recovery.state('account'), {
                    'passwordHash': None, 'version': 0
                })
                rpc.assert_not_called()


if __name__ == '__main__':
    unittest.main()
