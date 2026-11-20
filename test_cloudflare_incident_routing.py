"""Cloudflare incidents use Bob's existing canonical, public-safe error panel."""
import unittest
from bob_issue_watchdog import CODES, EXTERNAL_CODES, issue_title, sync_issue
from bob_problems import from_issues


class TestCloudflareIssueRouting(unittest.TestCase):
    def test_cloudflare_codes_are_known_and_externally_verified(self):
        for code in ("cloudflare-worker-error", "cloudflare-observability-coverage"):
            self.assertIn(code, CODES)
            self.assertIn(code, EXTERNAL_CODES)
            self.assertTrue(issue_title(code).startswith("[Bob KI-Hilfe] "))

    def test_missing_cloudflare_codes_cannot_auto_close(self):
        code = "cloudflare-worker-error"
        issue = {
            "number": 999991, "title": issue_title(code), "body": "",
            "user": {"login": "github-actions[bot]"},
            "created_at": "2026-11-20T12:00:00Z",
            "updated_at": "2026-11-20T12:00:00Z",
        }
        writes = []

        def request(method, path, *, token, repo, data=None):
            if method == "GET":
                if path.startswith("/search/issues"):
                    return {"items": [issue], "total_count": 1,
                            "incomplete_results": False}
                if path.startswith("/issues?state=open"):
                    return [issue]
            writes.append((method, path, data))
            return {}

        status = sync_issue([], token="test", repo="ichrob/gold-dashboard1",
                            requester=request,
                            at="2026-11-20T12:10:00Z",
                            recovery_codes={code})
        self.assertEqual(status, "already-open")
        self.assertFalse(writes, "Cloudflare issue closed without Cloudflare recovery proof")

    def test_bob_problem_panel_accepts_fixed_cloudflare_code(self):
        row = {"number": 999991, "title": issue_title("cloudflare-worker-error"),
               "user": {"login": "github-actions[bot]"}, "body": "",
               "created_at": "2026-11-20T12:00:00Z",
               "updated_at": "2026-11-20T12:00:00Z"}
        items = from_issues([row])["problems"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "cloudflare-worker-error")
        self.assertEqual(items[0]["message"], CODES["cloudflare-worker-error"])


if __name__ == "__main__":
    unittest.main()
