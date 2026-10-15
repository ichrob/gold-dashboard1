import unittest
import json
import re
import bob_problems as problems
import bob_issue_watchdog as watchdog


def issue(code, number):
    return {
        "number": number,
        "title": watchdog.issue_title(code),
        "created_at": "2026-10-12T12:00:00Z",
        "body": "private, not for API response",
        "html_url": "https://untrusted.example/unsafe",
        "state": "open",
    }


class BobProblemsTests(unittest.TestCase):
    def setUp(self):
        problems._CACHED = None
        problems._LAST_TRY = 0.0

    def test_one_two_three_open_incidents(self):
        rows = [issue("scanner-unreachable", 101),
                issue("push-unreachable", 102),
                issue("paper-unhealthy", 103)]
        self.assertEqual(problems.from_issues(rows[:1])["count"], 1)
        self.assertEqual(problems.from_issues(rows[:2])["count"], 2)
        self.assertEqual(problems.from_issues(rows)["count"], 3)
        self.assertEqual(problems.from_issues(rows[1:])["count"], 2)
        self.assertEqual(problems.from_issues([])["count"], 0)

    def test_untrusted_issues_and_pull_requests_excluded(self):
        rows = [
            issue("scanner-unreachable", 3),
            issue("scanner-unreachable", 99),  # avoid counting duplicates
            {"title": "Someone else's issue", "number": 5, "body": "do not show"},
            {**issue("push-unreachable", 6), "pull_request": {"url": "irrelevant"}},
            {**issue("paper-unhealthy", 8), "number": -2},
        ]
        data = problems.from_issues(rows)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["problems"][0]["url"],
                         "https://github.com/ichrob/gold-dashboard1/issues/3")
        self.assertNotIn("private", str(data))
        self.assertNotIn("untrusted.example", str(data))

    def test_cache_and_stale_response_never_invent_zero(self):
        calls = []
        def fetcher():
            calls.append(1)
            if len(calls) > 1:
                raise OSError("network unavailable")
            return [issue("scanner-unreachable", 1)]
        one = problems.snapshot(fetcher=fetcher, clock=lambda: 100)
        two = problems.snapshot(fetcher=fetcher, clock=lambda: 105)
        self.assertEqual((one["count"], two["count"]), (1, 1))
        self.assertEqual(len(calls), 1)
        stale = problems.snapshot(fetcher=fetcher, clock=lambda: 701)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["count"], 1)

    def test_unavailable_distinct_from_no_open_problems(self):
        def offline():
            raise OSError("network unavailable")
        data = problems.snapshot(fetcher=offline, clock=lambda: 100)
        self.assertEqual(data["status"], "unavailable")
        self.assertIsNone(data["count"])
        self.assertEqual(problems.from_issues([])["count"], 0)

    def test_owner_curated_manual_ki_help_is_counted(self):
        manual = {
            "number": 351,
            "title": "[Bob KI-Hilfe] Offener Emittenten-Datenzugang",
            "user": {"login": "ichrob"},
            "created_at": "2026-10-12T20:00:00Z",
            "updated_at": "2026-10-12T20:10:00Z",
            "body": "untrusted technical details",
        }
        data = problems.from_issues([manual, issue("paper-unhealthy", 101)])
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["problems"][0]["code"], "manual-351")
        self.assertEqual(data["problems"][0]["message"], "Offener Emittenten-Datenzugang")
        self.assertNotIn("untrusted", str(data))
        self.assertEqual(problems.from_issues([dict(manual, user={"login": "attacker"})])["count"], 0)
        self.assertEqual(problems.from_issues([dict(manual, title="Unrelated")])["count"], 0)
        self.assertEqual(problems.from_issues([dict(manual, title="[Bob KI-Hilfe] " + "x"*151)])["count"], 0)

    def test_trusted_ki_status_marker_only_and_no_body_leak(self):
        row = issue("product-quote-evidence-missing", 410)
        row["user"] = {"login": "github-actions[bot]"}
        row["body"] = "Technical text: PRIVATE_DETAILS_SHOULD_NEVER_LEAK\\n<!-- BOB_KI_STATUS:in-progress -->"
        result = problems.from_issues([row])
        self.assertEqual(result["problems"][0]["kiStatus"], "in-progress")
        self.assertEqual(result["problems"][0]["kiStatusLabel"], "KI prüft die Ursache")
        self.assertNotIn("PRIVATE_DETAILS_SHOULD_NEVER_LEAK", str(result))
        row["body"] = "<!-- BOB_KI_STATUS:waiting-for-evidence -->"
        self.assertEqual(problems.from_issues([row])["problems"][0]["kiStatus"], "waiting-for-evidence")
        row["body"] = "<!-- BOB_KI_STATUS:done -->"
        self.assertEqual(problems.from_issues([row])["problems"][0]["kiStatus"], "new")
        row["body"] = "<!-- BOB_KI_STATUS:testing -->"
        row["user"] = {"login": "unknown-public-author"}
        self.assertEqual(problems.from_issues([row])["problems"][0]["kiStatus"], "new")

    def test_untrusted_status_text_and_browser_fallback_sanitization(self):
        row = issue("scanner-degraded", 34)
        row["user"] = {"login": "ichrob"}
        row["body"] = "Somebody wrote <!-- BOB_KI_STATUS:testing --> in prose"
        self.assertEqual(problems.from_issues([row])["problems"][0]["kiStatus"], "new")
        row["body"] = "<!-- BOB_KI_STATUS:testing -->"
        self.assertEqual(problems.from_issues([row])["problems"][0]["kiStatus"], "testing")
        self.assertIn("issue.body.matchAll(", problems.PANEL)
        self.assertIn("kiStatusLabels[kiStatus]", problems.PANEL)
        self.assertIn("issue.kiStatusLabel||kiStatusLabels.new", problems.PANEL)

    def test_outage_has_shorter_retry_than_success(self):
        attempts = []
        def offline():
            attempts.append(1)
            raise OSError("unavailable")
        self.assertEqual(problems.snapshot(fetcher=offline, clock=lambda: 100)["status"], "unavailable")
        problems.snapshot(fetcher=offline, clock=lambda: 200)
        self.assertEqual(len(attempts), 1)
        problems.snapshot(fetcher=offline, clock=lambda: 221)
        self.assertEqual(len(attempts), 2)

    def test_ui_fetches_private_counters_separately(self):
        self.assertIn("fetch('/api/repair-statistics'", problems.PANEL)
        self.assertIn("void refreshStatistics();", problems.PANEL)
        self.assertIn("await publicIndex()", problems.PANEL)
        self.assertIn("public-github-browser", problems.PANEL)

    def test_browser_fallback_includes_all_product_categories(self):
        match=re.search(r'const publicCodes=(\{.*?\});',problems.PANEL)
        self.assertEqual(json.loads(match.group(1)),watchdog.CODES)
        self.assertNotIn('__BOB_PUBLIC_CODES__',problems.PANEL)

    def test_legacy_issue_is_one_problem(self):
        data = problems.from_issues([{
            "title": watchdog.ISSUE_TITLE,
            "number": 88,
            "created_at": "2026-10-12T12:00:00Z",
        }])
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["problems"][0]["code"], "legacy-incident")

    def test_ui_exposes_independent_copy_action(self):
        self.assertIn("data-problem-count", problems.PANEL + " data-problem-count")
        self.assertIn("KI-Hilfebericht kopieren", problems.PANEL)
        self.assertIn("document.createElement('article')", problems.PANEL)


if __name__ == "__main__":
    unittest.main()
