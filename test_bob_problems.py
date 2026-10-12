import unittest
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
        stale = problems.snapshot(fetcher=fetcher, clock=lambda: 191)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["count"], 1)

    def test_unavailable_distinct_from_no_open_problems(self):
        def offline():
            raise OSError("network unavailable")
        data = problems.snapshot(fetcher=offline, clock=lambda: 100)
        self.assertEqual(data["status"], "unavailable")
        self.assertIsNone(data["count"])
        self.assertEqual(problems.from_issues([])["count"], 0)

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
