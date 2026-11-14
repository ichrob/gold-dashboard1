"""No-network regression checks for owner's opt-in to existing Cloudflare Free AI."""
import os
import unittest
from unittest.mock import Mock, patch
import ai_peer_review as base
import ai_peer_review_free as reviewer

SHA = "a"*40
MARKER = base.OPT_IN_MARKER

def owned(body, *, draft=False, head=SHA, owner="ichrob", fork=False):
    return {"state":"open","draft":draft,
            "base":{"repo":{"full_name":base.REPO}},
            "head":{"repo":{"full_name":"other/fork" if fork else base.REPO},"sha":head},
            "user":{"login":owner},"body":body}

class CloudflareFreeOptInTests(unittest.TestCase):
    def test_exact_marker_only_and_case_reference_not_weakened(self):
        self.assertTrue(base.automatic_review_requested(MARKER))
        self.assertFalse(base.automatic_review_requested(""))
        self.assertFalse(base.automatic_review_requested(MARKER+" "+MARKER))
        self.assertFalse(base.automatic_review_requested(MARKER+" BOB-25-unknown-code"))
        self.assertFalse(base.automatic_review_requested(None))
        self.assertFalse(base.automatic_review_requested("x"*10001+MARKER))

    def test_owned_current_ci_ready_pr_can_opt_in(self):
        with patch.dict(os.environ, {"BOB_AI_AUTO_REVIEW_ENABLED":"1"}):
            self.assertEqual(base.review_allowed(owned(MARKER),mode="automatic",head_sha=SHA),SHA)
            for candidate in (
                owned(MARKER,draft=True),
                owned(MARKER,head="b"*40),
                owned(MARKER,owner="untrusted"),
                owned(MARKER,fork=True),
                owned(MARKER+" "+MARKER),
                owned("ordinary")):
                with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                    base.review_allowed(candidate,mode="automatic",head_sha=SHA)

    def test_existing_no_optin_ordinary_pr_remains_no_call(self):
        env={"BOB_AI_FREE_ONLY":"confirmed-workers-free",
             "BOB_AI_MODE":"automatic", "GITHUB_TOKEN":"ci-only",
             "BOB_PR_NUMBER":"1645"}
        with patch.dict(os.environ,env,clear=True),\
             patch.object(reviewer,"request_json",return_value=owned("ordinary")) as api,\
             patch.object(reviewer,"github_oidc") as oidc,\
             patch.object(reviewer,"cloudflare_review") as ai:
            self.assertIsNone(reviewer.main())
            self.assertEqual(api.call_count,1)
            oidc.assert_not_called()
            ai.assert_not_called()

    def test_opted_in_pr_uses_existing_oidc_worker_with_bounded_review(self):
        env={"BOB_AI_FREE_ONLY":"confirmed-workers-free",
             "BOB_AI_AUTO_REVIEW_ENABLED":"1",
             "BOB_AI_MODE":"automatic", "GITHUB_TOKEN":"ci-only",
             "BOB_PR_NUMBER":"1645","BOB_CI_HEAD_SHA":SHA}
        def network(url, token, method="GET", payload=None):
            if "/pulls/1645/files?" in url:
                return [{"filename":"pure_research.py",
                         "patch":"@@ -1,1 +1,2 @@\n+result = 2\n+assert result > 0"}]
            if "/issues/1645/comments?" in url:return []
            if "/issues/1645/comments" in url and method=="POST":
                self.assertIn("Unabhängige Zweit-KI",payload["body"])
                return {"id":1}
            if url.endswith("/pulls/1645"):return owned(MARKER)
            self.fail("Unexpected network call")
        with patch.dict(os.environ,env,clear=True),\
             patch.object(reviewer,"request_json",side_effect=network) as api,\
             patch.object(reviewer,"github_oidc",return_value="mock-oidc") as oidc,\
             patch.object(reviewer,"cloudflare_review",return_value="Kein belegbarer Fehler.") as ai:
            reviewer.main()
            self.assertEqual(api.call_count,4)
            self.assertEqual(oidc.call_count,1)
            self.assertEqual(ai.call_count,1)

    def test_optin_cannot_override_provider_or_review_quotas(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):
                base.review_allowed(owned(MARKER),mode="automatic",head_sha=SHA)
        with self.assertRaises(ValueError):
            base.check_review_budget([
                {"user":{"login":"github-actions[bot]"},
                 "body":base.REVIEW_MARKER+SHA+";utcday=2026-11-13 -->"}
            ],SHA,now=__import__("datetime").datetime(2026,11,13,
                  tzinfo=__import__("datetime").timezone.utc))

if __name__=="__main__":
    unittest.main()
