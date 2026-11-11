"""Offline safety checks; never require a Google API key or send a network call."""
import json
import os
from pathlib import Path
import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import gemini_peer_review_free as g


class GeminiReviewSafetyTests(unittest.TestCase):
    def test_opt_in_disabled_by_default(self):
        # Fixed clock avoids failing all of Bob CI when the model cutoff arrives.
        with patch.object(g, "datetime") as clock:
            clock.now.return_value.date.return_value = date(2026, 11, 9)
            with patch.dict(os.environ, {}, clear=True):
                self.assertFalse(g.enabled())
            with patch.dict(os.environ, {
                "BOB_GEMINI_FREE_ONLY": "confirmed-unbilled-free-project"
            }, clear=True):
                self.assertTrue(g.enabled())
            with patch.dict(os.environ, {
                "BOB_GEMINI_AUTO_REVIEW_ENABLED": "1"
            }, clear=True):
                self.assertFalse(g.enabled())
            with patch.dict(os.environ, {
                "BOB_GEMINI_FREE_ONLY": "confirmed-unbilled-free-project",
                "BOB_GEMINI_AUTO_REVIEW_ENABLED": "1",
            }, clear=True):
                self.assertTrue(g.enabled())
            with patch.dict(os.environ, {
                "BOB_GEMINI_FREE_ONLY": "confirmed-unbilled-free-project",
                "BOB_GEMINI_AUTO_REVIEW_ENABLED": "0",
            }, clear=True):
                self.assertFalse(g.enabled())

    def _owner_pr(self):
        return {"state": "open", "draft": False,
                "user": {"login": "ichrob"},
                "base": {"repo": {"full_name": "ichrob/gold-dashboard1"}},
                "head": {"repo": {"full_name": "ichrob/gold-dashboard1"},
                         "sha": "a" * 40}}

    def test_default_review_for_owner_pr_without_repair_marker(self):
        pr = self._owner_pr()
        self.assertEqual(
            g.reviewed_pr_sha(pr, mode="automatic", head_sha="a" * 40),
            "a" * 40)
        # A same-repo Gemini proposal opened by GitHub Actions is also reviewable.
        pr["user"]["login"] = "github-actions[bot]"
        self.assertEqual(g.reviewed_pr_sha(pr, mode="manual"), "a" * 40)

    def test_no_review_for_fork_stranger_draft_or_stale_ci(self):
        pr = self._owner_pr()
        cases = [
            {**pr, "user": {"login": "unknown"}},
            {**pr, "draft": True},
            {**pr, "head": {"repo": {"full_name": "other/fork"},
                             "sha": "a" * 40}},
            {**pr, "base": {"repo": {"full_name": "other/fork"}}},
        ]
        for bad in cases:
            with self.subTest(case=bad), self.assertRaises(ValueError):
                g.reviewed_pr_sha(bad, mode="automatic", head_sha="a" * 40)
        with self.assertRaisesRegex(ValueError, "draft-or-stale-ci"):
            g.reviewed_pr_sha(pr, mode="automatic", head_sha="b" * 40)
        with self.assertRaisesRegex(ValueError, "review-mode-denied"):
            g.reviewed_pr_sha(pr, mode="something-else")

    def test_owner_default_allow_and_explicit_revocation(self):
        self.assertTrue(g.owner_allows_review([]))
        comments = [
            {"id": 1, "user": {"login": "ichrob"},
             "body": "/bob-peer-review-off"},
            {"id": 2, "user": {"login": "external"},
             "body": "/bob-peer-review-on"},
            {"id": 3, "user": {"login": "github-actions[bot]"},
             "body": "/bob-peer-review-on"},
            {"id": 4, "user": {"login": "ichrob"},
             "body": "/bob-peer-review-on more text"},
        ]
        self.assertFalse(g.owner_allows_review(comments))
        comments.append({"id": 5, "user": {"login": "ichrob"},
                         "body": "/bob-peer-review-on"})
        self.assertTrue(g.owner_allows_review(comments))
        comments.append({"id": 6, "user": {"login": "ichrob"},
                         "body": "/bob-peer-review-off"})
        self.assertFalse(g.owner_allows_review(list(reversed(comments))))
        with self.assertRaisesRegex(ValueError, "review-history-incomplete"):
            g.owner_allows_review([{}] * 100)
        with self.assertRaisesRegex(ValueError, "review-history-incomplete"):
            g.owner_allows_review([{"user": {"login": "ichrob"},
                                    "body": "/bob-peer-review-off"}])

    def test_owner_veto_stops_api_call_even_when_review_enabled(self):
        pr = self._owner_pr()
        comments = [{"id": 123, "user": {"login": "ichrob"},
                     "body": "/bob-peer-review-off"}]
        env = {"GITHUB_TOKEN": "github-token",
               "GEMINI_API_KEY": "a" * 40,
               "BOB_PR_NUMBER": "1563",
               "BOB_GEMINI_MODE": "automatic",
               "BOB_CI_HEAD_SHA": "a" * 40}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(g, "enabled", return_value=True), \
             patch.object(g, "request_json", side_effect=[pr, comments]) as api, \
             patch.object(g, "gemini_request") as model:
            g.run()
            model.assert_not_called()
            self.assertEqual(api.call_count, 2)

    def test_revocation_during_model_call_blocks_publication(self):
        pr = self._owner_pr()
        off = [{"id": 124, "user": {"login": "ichrob"},
                "body": "/bob-peer-review-off"}]
        env = {"GITHUB_TOKEN": "github-token",
               "GEMINI_API_KEY": "a" * 40,
               "BOB_PR_NUMBER": "1563",
               "BOB_GEMINI_MODE": "automatic",
               "BOB_CI_HEAD_SHA": "a" * 40}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(g, "enabled", return_value=True), \
             patch.object(g, "request_json", side_effect=[pr, [], [], off]) as api, \
             patch.object(g, "safe_files", return_value="FILE: example.py\n@@ -1 +1 @@") as safe, \
             patch.object(g, "gemini_request", return_value="Kein Fehler.") as model:
            g.run()
            safe.assert_called_once()
            model.assert_called_once()
            self.assertEqual(api.call_count, 4)
            self.assertFalse(any(call.args[0].endswith("/comments")
                                 for call in api.call_args_list))

    def test_model_sunset_fails_closed(self):
        with patch.dict(os.environ, {
            "BOB_GEMINI_FREE_ONLY": "confirmed-unbilled-free-project",
            "BOB_GEMINI_AUTO_REVIEW_ENABLED": "1",
        }, clear=True), patch.object(g, "datetime") as clock:
            clock.now.return_value.date.return_value = date(2027, 1, 1)
            self.assertFalse(g.enabled())

    def test_request_has_bounded_thinking_and_no_real_network(self):
        reply = {"candidates": [{"content": {"parts": [{"text": "Keine Regression."}]}}]}
        fake_opener = MagicMock()
        fake_opener.open.return_value.__enter__.return_value.read.return_value = (
            json.dumps(reply).encode("utf-8")
        )
        with patch.object(g.urllib.request, "build_opener", return_value=fake_opener):
            answer = g.gemini_request("PUBLIC-DIFF: test case", "x" * 32)
        self.assertEqual(answer, "Keine Regression.")
        request = fake_opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"], "minimal")
        self.assertNotIn("temperature", payload["generationConfig"])
        self.assertIn("gemini-3.5-flash-lite:generateContent", request.full_url)
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 1800)

    def test_budget_rejects_incomplete_history(self):
        with self.assertRaises(ValueError):
            g.review_budget([{}] * 100, "a" * 40)
        with self.assertRaises(ValueError):
            g.review_budget([], "wrong")

    def test_duplicate_same_sha(self):
        sha = "b" * 40
        rows = [{"user": {"login": "github-actions[bot]"},
                 "body": g.MARKER + sha + ";utcday=2026-11-09 -->\nreview"}]
        self.assertIsNone(g.review_budget(rows, sha))

    def test_two_per_day(self):
        day = datetime(2026, 11, 9, tzinfo=timezone.utc)
        rows = [{"user": {"login": "github-actions[bot]"},
                 "body": g.MARKER + (str(i) * 40) + ";utcday=2026-11-09 -->"}
                for i in (1, 2)]
        self.assertIsNone(g.review_budget(rows, "a" * 40, now=day))
        self.assertEqual(g.review_budget(rows[:1], "a" * 40, now=day),
                         "2026-11-09")

    def test_other_bot_comments_do_not_count(self):
        day = datetime(2026, 11, 9, tzinfo=timezone.utc)
        rows = [{"user": {"login": "someone-else"},
                 "body": g.MARKER + "a" * 40 + ";utcday=2026-11-09 -->"}]
        self.assertEqual(g.review_budget(rows, "b" * 40, now=day), "2026-11-09")

    def test_provider_request_refuses_short_key_before_network(self):
        with self.assertRaises(ValueError):
            g.gemini_request("A" * 100, "invalid")
        with self.assertRaises(ValueError):
            g.gemini_request("short", "x" * 50)

    def test_github_pr_timeline_comment_permissions(self):
        workflow = Path(".github/workflows/bob-gemini-free-review.yml").read_text()
        self.assertIn("issues: write", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertNotIn("pull-requests: read", workflow)

    def test_no_network_when_unconfigured(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(g, "request_json") as api:
            g.run()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
