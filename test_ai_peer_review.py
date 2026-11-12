import os
import unittest
from unittest.mock import patch

import ai_peer_review as peer


class SecondAI(unittest.TestCase):
    def test_no_billing_attestation_blocks_all_calls(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(peer, "request_json") as send:
                with self.assertRaisesRegex(ValueError, "free-account-unconfirmed"):
                    peer.main()
                send.assert_not_called()

    def test_no_api_credentials_or_valid_pr_blocks_all_calls(self):
        with patch.dict(os.environ, {"BOB_AI_FREE_ONLY": "confirmed-workers-free"}, clear=True):
            with patch.object(peer, "request_json") as send:
                with self.assertRaisesRegex(ValueError, "missing-config"):
                    peer.main()
                send.assert_not_called()

    def test_secret_or_non_source_diffs_rejected(self):
        for item in [
            {"filename": "server.py", "patch": "+api_key = 'sensitive'"},
            {"filename": "server.py", "patch": "+Authorization: Bearer test"},
            {"filename": ".env", "patch": "+VAR=not-public"},
        ]:
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, "no-safe"):
                peer.safe_files([item])

    def test_bounded_public_patch(self):
        diff = peer.safe_files([{"filename": "server.py", "patch": "@@ -1 +1 @@\n-old()\n+new()"}])
        self.assertIn("server.py", diff)
        self.assertIn("+new()", diff)
        with self.assertRaisesRegex(ValueError, "no-safe"):
            peer.safe_files([{"filename": "server.py", "patch": "a" * 4501}])

    def test_bounded_public_html_patch_is_reviewable(self):
        diff = peer.safe_files([{
            "filename": "Bob.html",
            "patch": "@@ -1 +1 @@\n-<main>old</main>\n+<main>new</main>",
        }])
        self.assertIn("FILE: Bob.html", diff)
        self.assertIn("+<main>new</main>", diff)

    def test_invalid_cloudflare_responses_never_publish(self):
        for data in [{"success": False}, {"success": True, "result": {"response": ""}}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                peer.review_response(data)
        out = peer.review_response({"success": True, "result": {"response": "See https://bad.example"}})
        self.assertNotIn("https://", out)

    def test_prompt_never_supplies_tools_or_order_actions(self):
        prompt = peer.provider_payload("FILE: x.py\n+pass")
        self.assertEqual(len(prompt["messages"]), 2)
        self.assertNotIn("tools", prompt)
        self.assertEqual(prompt["max_tokens"], 1200)


    def test_auto_review_rejects_forks_drafts_and_stale_ci(self):
        sha = "a" * 40
        pr = {"state": "open", "user": {"login": "ichrob"},
              "base": {"repo": {"full_name": peer.REPO}},
              "head": {"repo": {"full_name": peer.REPO}, "sha": sha},
              "draft": False, "body": "Fixes BOB-12-push-unhealthy"}
        with patch.dict(os.environ, {"BOB_AI_AUTO_REVIEW_ENABLED": "1"}, clear=True):
            self.assertEqual(peer.review_allowed(pr, mode="automatic", head_sha=sha), sha)
            with self.assertRaises(ValueError):
                peer.review_allowed(pr, mode="automatic", head_sha="b" * 40)
            with self.assertRaises(ValueError):
                peer.review_allowed(pr | {"draft": True}, mode="automatic", head_sha=sha)
            with self.assertRaises(ValueError):
                peer.review_allowed(pr | {"user": {"login": "unknown"}}, mode="automatic", head_sha=sha)
            with self.assertRaises(ValueError):
                peer.review_allowed(pr | {"body": "No evidence linked"}, mode="automatic", head_sha=sha)
            with self.assertRaises(ValueError):
                peer.review_allowed(pr | {"head": {"repo": {"full_name": "someone/fork"}, "sha": sha}},
                                    mode="automatic", head_sha=sha)

    def test_auto_review_is_opt_in_only(self):
        sha = "a" * 40
        pr = {"state": "open", "user": {"login": "ichrob"},
              "base": {"repo": {"full_name": peer.REPO}},
              "head": {"repo": {"full_name": peer.REPO}, "sha": sha},
              "draft": False, "body": "BOB-12-push-unhealthy"}
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            peer.review_allowed(pr, mode="automatic", head_sha=sha)

    def test_second_ai_has_per_commit_and_daily_budget(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 9, tzinfo=timezone.utc)
        sha = "a" * 40
        self.assertEqual(peer.check_review_budget([], sha, now=now), "2026-11-09")
        c1 = {"user": {"login": "github-actions[bot]"},
              "body": peer.REVIEW_MARKER + "b" * 40 + ";utcday=2026-11-09 -->"}
        c2 = {"user": {"login": "github-actions[bot]"},
              "body": peer.REVIEW_MARKER + "c" * 40 + ";utcday=2026-11-09 -->"}
        with self.assertRaisesRegex(ValueError, "already-reviewed"):
            peer.check_review_budget([c1], "b" * 40, now=now)
        with self.assertRaisesRegex(ValueError, "daily-review-limit"):
            peer.check_review_budget([c1, c2], sha, now=now)
        with self.assertRaisesRegex(ValueError, "comment-history-incomplete"):
            peer.check_review_budget([{}] * 100, sha, now=now)



if __name__ == "__main__":
    unittest.main()
