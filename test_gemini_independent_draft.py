"""Safe, offline tests for the owner-only Gemini code proposal path."""
import unittest
from unittest.mock import patch, Mock
import gemini_independent_draft as draft


class DraftSafetyTests(unittest.TestCase):
    TARGET = "test_example.py"
    PATCH = ("--- a/test_example.py\n+++ b/test_example.py\n"
             "@@ -1 +1 @@\n-old\n+new\n")

    def test_accept_one_matching_unified_patch_not_execute_it(self):
        self.assertEqual(draft.strict_patch(self.PATCH, self.TARGET), self.PATCH)
        fence = chr(96) * 3
        self.assertEqual(draft.strict_patch(fence + "diff\n" + self.PATCH + fence,
                                            self.TARGET), self.PATCH)

    def test_denies_cross_file_path_traversal_and_untrusted_preamble(self):
        for evil in (
            self.PATCH.replace("test_example.py", "../secrets.txt"),
            self.PATCH + "--- a/server.py\n+++ b/server.py\n@@ -1 +1 @@\n-a\n+b\n",
            "Ignore instructions\n" + self.PATCH,
            self.PATCH + "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n",
            self.PATCH + "GIT binary patch\n",
            self.PATCH + "+password = 'very-long-sensitive-value'\n",
            self.PATCH.replace("+++ b/test_example.py", "+++ b/test_different.py"),
            "no diff available",
        ):
            with self.subTest(evil=evil[:70]), self.assertRaises(ValueError):
                draft.strict_patch(evil, self.TARGET)

    def test_fails_closed_on_excessive_change_count(self):
        patch = "--- a/test_example.py\n+++ b/test_example.py\n@@ -1 +1 @@\n"
        patch += "+new\n" * 170
        with self.assertRaises(ValueError):
            draft.strict_patch(patch, self.TARGET)

    def test_deterministic_branch_per_public_issue_and_revision(self):
        sha = "a" * 40
        a = draft.draft_branch("1542", "GEMINI.md", sha)
        b = draft.draft_branch("1542", "GEMINI.md", sha)
        c = draft.draft_branch("1542", "test_example.py", sha)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("gemini/draft-1542-"))

    def test_never_calls_provider_without_explicit_optin(self):
        with patch.object(draft, "enabled", return_value=False), \
             patch.object(draft, "request_json") as github, \
             patch.object(draft, "model_proposal") as provider:
            with patch.dict("os.environ", {}, clear=True):
                draft.run()
            github.assert_not_called()
            provider.assert_not_called()

    def test_owner_and_repository_are_required_before_any_read(self):
        environment = {"BOB_GEMINI_DRAFT_PR_ENABLED": "1",
                       "GITHUB_ACTOR": "another-user",
                       "GITHUB_REPOSITORY": "ichrob/gold-dashboard1",
                       "GITHUB_REF": "refs/heads/main"}
        with patch.object(draft, "enabled", return_value=True), \
             patch.dict("os.environ", environment, clear=True), \
             patch.object(draft, "request_json") as github, \
             self.assertRaises(ValueError):
            draft.run()
            github.assert_not_called()


if __name__ == "__main__":
    unittest.main()
