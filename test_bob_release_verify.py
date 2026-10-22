import unittest
from tools.bob_release_verify import verify

SHA = "a"*40
OLD = "b"*40


class ReleaseVerificationTests(unittest.TestCase):
    def test_exact_same_sha_on_both_healthy_services(self):
        verified, states = verify(SHA, {"status":"ok", "build":SHA},
                                       {"ok":True, "build":SHA})
        self.assertTrue(verified)
        self.assertEqual(states, {"scanner":"verified", "push":"verified"})

    def test_old_scan_build_is_never_a_verified_release(self):
        verified, states = verify(SHA, {"status":"ok", "build":OLD},
                                       {"ok":True, "build":SHA})
        self.assertFalse(verified)
        self.assertEqual(states["scanner"], "build-mismatch-or-unknown")

    def test_liveness_without_sha_or_push_is_not_a_release(self):
        for scan, push in [({"status":"ok"}, {"ok":True,"build":SHA}),
                           ({"status":"ok","build":SHA}, None),
                           ({"status":"degraded","build":SHA}, {"ok":True,"build":SHA}),
                           ({"status":"ok","build":SHA}, {"ok":False,"build":SHA})]:
            with self.subTest(scan=scan, push=push):
                self.assertFalse(verify(SHA, scan, push)[0])

    def test_only_full_sha_allowed(self):
        self.assertFalse(verify("main", {}, {})[0])
        self.assertFalse(verify("a"*10, {}, {})[0])


if __name__ == "__main__":
    unittest.main()
