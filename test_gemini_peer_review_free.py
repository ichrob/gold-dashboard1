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
                self.assertFalse(g.enabled())
            with patch.dict(os.environ, {
                "BOB_GEMINI_AUTO_REVIEW_ENABLED": "1"
            }, clear=True):
                self.assertFalse(g.enabled())
            with patch.dict(os.environ, {
                "BOB_GEMINI_FREE_ONLY": "confirmed-unbilled-free-project",
                "BOB_GEMINI_AUTO_REVIEW_ENABLED": "1",
            }, clear=True):
                self.assertTrue(g.enabled())

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
