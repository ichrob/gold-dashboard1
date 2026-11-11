"""Offline tests for mobile Gemini developer suggestion workflow, no external calls."""
import base64
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import gemini_mobile_developer as g


class GeminiMobileDeveloperTests(unittest.TestCase):
    def test_disabled_without_free_project_and_after_expiry(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(g.enabled())
        with patch.dict(os.environ, {"BOB_GEMINI_FREE_ONLY":
                                   "confirmed-unbilled-free-project"}, clear=True):
            with patch.object(g, "datetime") as clock:
                clock.now.return_value.date.return_value = date(2026, 11, 9)
                self.assertTrue(g.enabled())
                clock.now.return_value.date.return_value = date(2027, 1, 1)
                self.assertFalse(g.enabled())

    def test_allowlisted_single_public_file_only(self):
        for p in ("test_signal.py", "gemini_peer_review_free.py", "GEMINI.md",
                  "docs/public-notes.md"):
            self.assertEqual(g.checked_path(p), p)
        for p in ("../config", ".github/workflows/run.yml", "render.yaml",
                  "bob_oauth_store.py", "termux_maintenance.py",
                  "src/../../secrets.py", "test_foo.py;curl evil",
                  "key.json", "", "docs/a.txt"):
            with self.subTest(path=p), self.assertRaises(ValueError):
                g.checked_path(p)

    def test_issue_must_be_public_owner_issue(self):
        item = {"state": "open", "user": {"login": "ichrob"},
                "title": "Fix the public regression",
                "body": "Add an independent unit test for these known public records."}
        self.assertIn("regression", g.public_issue(item))
        for invalid in (
            {**item, "user": {"login": "external-user"}},
            {**item, "pull_request": {}},
            {**item, "state": "closed"},
            {**item, "body": "password=abc123456789abcdefghijkl"},
        ):
            with self.assertRaises(ValueError):
                g.public_issue(invalid)

    def test_long_owner_issue_from_github_is_accepted_but_bounded(self):
        # Issue #1497 is longer than the original 4,400-character limit.
        item = {"state": "open", "user": {"login": "ichrob"},
                "title": "Gemini developer integration",
                "body": "Public requirements. " * 250}
        self.assertGreater(len(item["title"] + item["body"]), 4400)
        self.assertLess(len(item["title"] + item["body"]), 7000)
        self.assertIn("Public requirements.", g.public_issue(item))
        item["body"] = "Public requirements. " * 400
        with self.assertRaises(ValueError):
            g.public_issue(item)

    def test_public_file_validation(self):
        source = "# public module\n" + "x = True\n" * 20
        encoded = base64.b64encode(source.encode()).decode()
        obj = {"encoding": "base64", "sha": "a" * 40, "content": encoded}
        self.assertEqual(g.public_file(obj), source)
        with self.assertRaises(ValueError):
            g.public_file({**obj, "sha": "wrong"})
        with self.assertRaises(ValueError):
            g.public_file({**obj, "content": base64.b64encode(
                b"password=veryLongSensitivePassword").decode()})

    def test_public_file_longer_guide_has_bounded_limit(self):
        source = "# public notes\n" + "evidence checked\n" * 430
        obj = {"encoding": "base64", "sha": "a" * 40,
               "content": base64.b64encode(source.encode()).decode()}
        self.assertGreater(len(source), 6500)
        self.assertLessEqual(len(source), 8000)
        self.assertEqual(g.public_file(obj), source)
        too_long = "#" + "x" * 8000
        with self.assertRaises(ValueError):
            g.public_file({**obj, "content": base64.b64encode(
                too_long.encode()).decode()})

    def test_draft_prompt_requests_pure_diff(self):
        diff = "--- a/GEMINI.md\n+++ b/GEMINI.md\n@@ -1 +1 @@\n-old\n+new"
        response = {"candidates": [{"content": {"parts": [{"text": diff}]}}]}
        fake = MagicMock()
        fake.open.return_value.__enter__.return_value.read.return_value = (
            json.dumps(response).encode())
        with patch.object(g.urllib.request, "build_opener", return_value=fake):
            self.assertEqual(g.model_proposal("Public task", "GEMINI.md",
                                              "# small public file", "a" * 40,
                                              patch_only=True), diff)
        request = fake.open.call_args.args[0]
        prompt = json.loads(request.data)["systemInstruction"]["parts"][0]["text"]
        self.assertIn("NUR", prompt)
        self.assertIn("keine Einleitung", prompt)

    def test_dedup_and_budget(self):
        marker = g.MARKER + "issue=1497;fingerprint=abc;day=2026-11-09 -->"
        comments = [{"user": {"login": "github-actions[bot]"}, "body": marker + "\nA"}]
        self.assertTrue(g.already_requested(comments, marker, "2026-11-09"))
        self.assertFalse(g.already_requested(comments, marker + "other", "2026-11-10"))
        two = comments + [{"user": {"login": "github-actions[bot]"},
                           "body": g.MARKER + "new;day=2026-11-09 -->"}]
        with self.assertRaises(ValueError):
            g.already_requested(two, marker + "other", "2026-11-09")
        with self.assertRaises(ValueError):
            g.already_requested([{}] * 100, marker, "2026-11-09")

    def test_model_request_has_bounded_tokens_and_no_actual_network(self):
        patch_text = "--- a/test_sample.py\n+++ b/test_sample.py\n@@ -1,1 +1,1 @@\n-old = True\n+new = True"
        response = {"candidates": [{"content": {"parts": [{"text": patch_text}]}}]}
        fake = MagicMock()
        fake.open.return_value.__enter__.return_value.read.return_value = (
            json.dumps(response).encode()
        )
        with patch.object(g.urllib.request, "build_opener", return_value=fake):
            actual = g.model_proposal("Issue text", "test_sample.py",
                                      "# public source", "a" * 40)
        self.assertEqual(actual, patch_text)
        request = fake.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 1900)
        self.assertEqual(payload["generationConfig"]["thinkingConfig"]["thinkingLevel"],
                         "minimal")
        self.assertIn("gemini-3.5-flash-lite", request.full_url)

    def test_rejects_empty_and_malformed_diff(self):
        for invalid in (
            "--- GEMINI.md",
            "Patch idea only",
            "--- a/GEMINI.md\n+++ b/GEMINI.md",
            "--- a/GEMINI.md\n+++ b/GEMINI.md\n@@ -1,1 +1,1 @@",
            "--- a/GEMINI.md\n+++ b/GEMINI.md\n@@ -1,1 +1,1 @@\n+",
        ):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    ValueError, "model-no-valid-diff"):
                g.verified_diff_or_explanation(invalid, "GEMINI.md")
        good = ("--- a/GEMINI.md\n+++ b/GEMINI.md\n"
                "@@ -1,1 +1,1 @@\n-Alt\n+Neu")
        self.assertEqual(g.verified_diff_or_explanation(good, "GEMINI.md"), good)
        refusal = "nicht sicher änderbar: " + "Die öffentliche Beweislage ist unzureichend. " * 3
        self.assertEqual(g.verified_diff_or_explanation(refusal, "GEMINI.md"), refusal)

    def test_no_external_call_without_free_project_or_key(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(g, "request_json") as api:
            g.run()
            api.assert_not_called()
        with patch.dict(os.environ, {"BOB_GEMINI_FREE_ONLY":
                                   "confirmed-unbilled-free-project",
                                   "BOB_GEMINI_DEV_ISSUE": "1497",
                                   "BOB_GEMINI_DEV_FILE": "GEMINI.md"}, clear=True):
            with patch.object(g, "request_json") as api:
                g.run()
                api.assert_not_called()

    def test_gemini_md_references_existing_safe_phone_workflow(self):
        guide = Path("GEMINI.md").read_text()
        self.assertLessEqual(len(guide), 8000)
        self.assertIn(".github/workflows/bob-gemini-mobile-developer.yml", guide)
        self.assertIn("BOB_GEMINI_MOBILE_DEVELOPER.md", guide)
        self.assertIn("/bob-gemini-dev GEMINI.md", guide)
        self.assertIn("keinen Code aus", guide)
        self.assertTrue(Path(".github/workflows/bob-gemini-mobile-developer.yml").is_file())
        self.assertTrue(Path("BOB_GEMINI_MOBILE_DEVELOPER.md").is_file())

    def test_workflow_manual_or_exact_owner_comment_without_code_write(self):
        source = Path(".github/workflows/bob-gemini-mobile-developer.yml").read_text()
        # Owner-only exact comment, no arbitrary user text reaching shell.
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("issue_comment:", source)
        self.assertIn("types: [created]", source)
        self.assertIn("github.event.comment.user.login == 'ichrob'", source)
        self.assertIn("github.event.comment.body == '/bob-gemini-dev GEMINI.md'", source)
        self.assertIn("!github.event.issue.pull_request", source)
        self.assertIn("github.event_name == 'workflow_dispatch'", source)
        self.assertIn("github.event.issue.number || inputs.issue_number", source)
        self.assertIn("'GEMINI.md' || inputs.target_file", source)
        self.assertIn("contents: read", source)
        self.assertIn("issues: write", source)
        self.assertNotIn("contents: write", source)
        self.assertNotIn("pull-requests: write", source)
        self.assertNotIn("id-token: write", source)
        self.assertNotIn("schedule:", source)
        self.assertIn("persist-credentials: false", source)


        source = Path(".github/workflows/bob-gemini-mobile-developer.yml").read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("contents: read", source)
        self.assertIn("issues: write", source)
        self.assertNotIn("contents: write", source)
        self.assertNotIn("pull-requests: write", source)
        self.assertNotIn("id-token: write", source)
        self.assertNotIn("schedule:", source)
        self.assertNotIn("issues:\n    types:", source)
        self.assertIn("persist-credentials: false", source)


if __name__ == "__main__":
    unittest.main()
