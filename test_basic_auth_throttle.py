import base64
import concurrent.futures
import unittest
from unittest.mock import patch
import bob_auth as auth

class BasicThrottleTests(unittest.TestCase):
    def setUp(self):
        auth.FAILURES.clear()
        auth.SESSIONS.clear()
        self.state = patch.object(auth.bob_recovery, 'state', return_value={'version':0,'passwordHash':None})
        self.state.start()
        self.addCleanup(self.state.stop)
        self.addCleanup(auth.FAILURES.clear)
        self.addCleanup(auth.SESSIONS.clear)

    def headers(self, password='wrong'):
        return {'Authorization':'Basic '+base64.b64encode(('user:'+password).encode()).decode()}

    def test_basic_budget_prevents_further_password_verification_and_expires(self):
        with patch.object(auth.time,'time',return_value=1000), patch.object(auth.bob_recovery,'matches',return_value=False) as verify:
            for _ in range(40): self.assertFalse(auth.authenticated(self.headers(),'user','secret'))
            self.assertEqual(verify.call_count,5)
        with patch.object(auth.time,'time',return_value=1299), patch.object(auth.bob_recovery,'matches') as verify:
            self.assertFalse(auth.authenticated(self.headers('secret'),'user','secret'))
            verify.assert_not_called()
        with patch.object(auth.time,'time',return_value=1301), patch.object(auth.bob_recovery,'matches',return_value=True):
            self.assertTrue(auth.authenticated(self.headers('secret'),'user','secret'))

    def test_form_and_basic_share_budget_and_success_does_not_reset_it(self):
        with patch.object(auth.time,'time',return_value=1000):
            auth.FAILURES.extend([1000]*4)
            self.assertTrue(auth.authenticated(self.headers('secret'),'user','secret'))
            self.assertEqual(len(auth.FAILURES),4)
            self.assertFalse(auth.check_password('user','wrong','user','secret',{'passwordHash':None}))
            with patch.object(auth.bob_recovery,'matches') as verify:
                self.assertFalse(auth.authenticated(self.headers('secret'),'user','secret'))
                verify.assert_not_called()
            self.assertIsNone(auth.check_password('user','secret','user','secret',{'passwordHash':None}))

    def test_valid_cookie_still_works_during_password_cooldown(self):
        with patch.object(auth.time,'time',return_value=1000):
            auth.FAILURES.extend([1000]*5)
            auth.SESSIONS['valid']=(2000,0)
            self.assertTrue(auth.authenticated({'Cookie':auth.COOKIE+'=valid'},'user','secret'))

    def test_concurrent_requests_cannot_exceed_budget(self):
        with patch.object(auth.time,'time',return_value=1000), patch.object(auth.bob_recovery,'matches',return_value=False) as verify:
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                list(pool.map(lambda _:auth.authenticated(self.headers(),'user','secret'),range(60)))
            self.assertEqual(verify.call_count,5)
            self.assertEqual(len(auth.FAILURES),5)

    def test_malformed_basic_is_bounded_and_counted(self):
        self.assertFalse(auth.authenticated({'Authorization':'Basic !!!'},'user','secret'))
        self.assertEqual(len(auth.FAILURES),1)
