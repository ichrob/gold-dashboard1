import hashlib
import ssl
import unittest
from unittest.mock import patch
import bob_auth as auth
import bob_recovery as recovery

class AuthRuntimeCostTests(unittest.TestCase):
    def test_verified_tls_configuration_reused_without_disabling_checks(self):
        context=auth.verified_tls_context()
        self.assertIs(context,auth.verified_tls_context())
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)

    def test_repeated_password_proof_binds_current_hash_and_candidate(self):
        encoded=recovery.hash_password('fixture-one')
        changed=recovery.hash_password('fixture-two')
        with patch.object(recovery,'_VERIFIED',{}), patch.object(recovery.hashlib,'pbkdf2_hmac',wraps=hashlib.pbkdf2_hmac) as derive:
            for _ in range(20):
                self.assertTrue(recovery.matches('fixture-one','',{'passwordHash':encoded}))
            self.assertEqual(derive.call_count,1)
            self.assertFalse(recovery.matches('fixture-two','',{'passwordHash':encoded}))
            self.assertFalse(recovery.matches('fixture-two','',{'passwordHash':encoded}))
            self.assertEqual(derive.call_count,3,'Failed attempts are never cached')
            self.assertFalse(recovery.matches('fixture-one','',{'passwordHash':changed}))
            self.assertTrue(recovery.matches('fixture-two','',{'passwordHash':changed}))
            self.assertFalse(recovery.matches('fixture-one','',{'passwordHash':None}))
            self.assertTrue(all(isinstance(k,bytes) and len(k)==32 for k in recovery._VERIFIED))

if __name__=='__main__':unittest.main()
