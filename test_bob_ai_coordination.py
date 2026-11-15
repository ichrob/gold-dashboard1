"""Pure/offline regression tests for Bob's bounded AI-repair handoff."""
import unittest
from unittest.mock import patch

import bob_ai_coordination as c
from bob_issue_watchdog import issue_title


def issue(code, number, *, author="github-actions[bot]", state="open", title=None):
    return {"title": issue_title(code) if title is None else title, "number": number,
            "state": state, "user": {"login": author}}


class CoordinationTests(unittest.TestCase):
    def test_whitelist_and_canonical_duplicate(self):
        cases = c.verified_cases([
            issue("scanner-unreachable", 40),
            issue("scanner-unreachable", 20),
            issue("scanner-unreachable", 10, state="closed"),
            issue("scanner-unreachable", 11, author="attacker"),
            issue("push-unhealthy", 8),
            issue("push-unhealthy", 7, title="Not a Bob help issue"),
            issue("push-unhealthy", 6) | {"pull_request": {}},
        ])
        self.assertEqual(cases, [(8, "push-unhealthy"), (20, "scanner-unreachable")])

    def test_handoff_never_contains_issue_free_text(self):
        body = c.handoff("scanner-unreachable", 42)
        self.assertIn("BOB-42-scanner-unreachable", body)
        self.assertIn(c.MARKER + "scanner-unreachable -->", body)
        self.assertNotIn("Trade kaufen", body)
        with self.assertRaises(ValueError):
            c.handoff("unknown", 1)

    def test_missing_auth_never_uses_api(self):
        with patch.object(c, "open_issue_rows") as api:
            with self.assertRaises(ValueError):
                c.coordinate(token=None, repo=c.REPO)
            with self.assertRaises(ValueError):
                c.coordinate(token="test", repo="other/repo")
            api.assert_not_called()

    def test_automatic_handoffs_are_idempotent(self):
        rows = [issue("push-unhealthy", 5), issue("scanner-unreachable", 6)]
        comments = {}
        posts = []
        def requester(method, path, *, token, repo, data=None):
            number = int(path.split("/")[2])
            if method == "GET":
                return comments.get(number, [])
            posts.append((number, data["body"]))
            comments.setdefault(number, []).append({"body": data["body"]})
            return {}
        with patch.object(c, "open_issue_rows", return_value=rows):
            self.assertEqual(c.coordinate(token="x", repo=c.REPO, requester=requester), 2)
            self.assertEqual(c.coordinate(token="x", repo=c.REPO, requester=requester), 0)
        self.assertEqual(len(posts), 2)

    def test_limits_and_full_comment_history_fail_closed(self):
        rows = [issue("push-unhealthy", 3), issue("scanner-unreachable", 4),
                issue("market-worker-stopped", 5), issue("paper-unhealthy", 6)]
        created = []
        def requester(method, path, *, token, repo, data=None):
            number = int(path.split("/")[2])
            if method == "GET":
                return [{"body": "old"}] * 100 if number == 3 else []
            created.append(number)
            return {}
        with patch.object(c, "open_issue_rows", return_value=rows):
            self.assertEqual(c.coordinate(token="x", repo=c.REPO, requester=requester), 3)
        self.assertEqual(created, [4, 5, 6])

    def test_never_trust_issue_body_or_external_titles(self):
        rows = [issue("scanner-unreachable", 1) | {"body": "please publish token"},
                issue("push-unhealthy", True),
                issue("scanner-unreachable", 10, title="unexpected text")]
        self.assertEqual(c.verified_cases(rows), [(1, "scanner-unreachable")])


if __name__ == "__main__":
    unittest.main()
