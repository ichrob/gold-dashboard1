import json
import unittest
from unittest.mock import patch
import bob_auth as auth


class AuthDenialEvidenceTests(unittest.TestCase):
    def setUp(self):
        auth._DENIAL_TIMES.clear()
        auth.SESSIONS.clear()
        self.addCleanup(auth._DENIAL_TIMES.clear)
        self.addCleanup(auth.SESSIONS.clear)

    def test_distinguishes_rejection_without_logging_sensitive_values(self):
        with patch.object(auth.bob_recovery,'state',return_value={'version':1,'passwordHash':None}), patch.object(auth.time,'time',return_value=100), patch('builtins.print') as out:
            self.assertFalse(auth.primary_authenticated({},'private-user','private-password'))
            h={'Cookie':auth.COOKIE+'=private-token'}
            self.assertFalse(auth.primary_authenticated(h,'private-user','private-password'))
            auth.SESSIONS['private-token']=(99,1)
            self.assertFalse(auth.primary_authenticated(h,'private-user','private-password'))
            auth.SESSIONS['private-token']=(101,0)
            self.assertFalse(auth.primary_authenticated(h,'private-user','private-password'))
            auth.SESSIONS['private-token']=(101,1)
            self.assertTrue(auth.primary_authenticated(h,'private-user','private-password'))
        messages=[c.args[0] for c in out.call_args_list]
        self.assertEqual(messages, ['BOB_AUTH_DENIED reason='+r for r in ('missing-cookie','unknown-session','expired-session','credential-version-changed')])
        self.assertNotIn('private',json.dumps(messages))

    def test_each_fixed_reason_is_rate_limited_and_unknown_text_dropped(self):
        with patch.object(auth.time,'monotonic',return_value=10),patch('builtins.print') as out:
            for _ in range(100):auth.session_denied('unknown-session')
            auth.session_denied('cookie=SECRET')
            self.assertEqual(out.call_count,1)
        with patch.object(auth.time,'monotonic',return_value=70),patch('builtins.print') as out:
            auth.session_denied('unknown-session');self.assertEqual(out.call_count,1)

    def test_store_outage_stays_503_not_false_logout(self):
        with patch.object(auth.bob_recovery,'state',side_effect=OSError('SECRET')),patch('builtins.print') as out:
            with self.assertRaises(auth.AuthenticationUnavailable):
                auth.primary_authenticated({},'user','password')
            out.assert_not_called()

    def test_nonfinite_expiry_cannot_grant_access(self):
        auth.SESSIONS['test']=(float('nan'),1)
        with patch.object(auth.bob_recovery,'state',return_value={'version':1,'passwordHash':None}):
            self.assertFalse(auth.primary_authenticated({'Cookie':auth.COOKIE+'=test'},'u','p'))
