import unittest

import bob_ai_quality_gate as q


def pr(body):
    return {"base": {"repo": {"full_name": q.REPO}}, "body": body}

def issue(code, number):
    from bob_issue_watchdog import issue_title
    return {"number": number, "title": issue_title(code)}


class GateTests(unittest.TestCase):
    def test_no_case_does_not_change_ordinary_pr_policy(self):
        self.assertEqual(q.inspect(pr("normal change"), None, []), "ordinary-pr")

    def test_linked_repair_needs_matching_issue_and_test_file(self):
        p = pr("Fix BOB-12-push-unhealthy")
        i = issue("push-unhealthy", 12)
        with self.assertRaisesRegex(ValueError, "repair-missing"):
            q.inspect(p, i, [{"filename": "push_server.py"}])
        self.assertEqual(q.inspect(p, i, [{"filename": "push_server.py"},
                              {"filename": "test_push_monitor.py"}]),
                         "repair-evidence-present-tests-still-need-to-pass")

    def test_code_and_issue_are_not_inferred(self):
        with self.assertRaisesRegex(ValueError, "unknown-repair"):
            q.inspect(pr("BOB-12-push-unhealthy"), issue("push-unhealthy", 13),
                      [{"filename": "test_something.py"}])
        with self.assertRaisesRegex(ValueError, "mismatched"):
            q.inspect(pr("BOB-12-push-unhealthy"), issue("push-unreachable", 12),
                      [{"filename": "test_something.py"}])
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            q.inspect(pr("BOB-12-push-unhealthy and BOB-13-scanner-unreachable"),
                      issue("push-unhealthy", 12), [{"filename": "test_something.py"}])

    def test_incomplete_page_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            q.inspect(pr("BOB-12-push-unhealthy"), issue("push-unhealthy", 12),
                      [{"filename": "test_ok.py"}] * 100)

    def test_reader_only_when_linked_and_trusted(self):
        calls = []
        def reader(path, token):
            calls.append(path)
            if path == "/pulls/25":
                return pr("BOB-12-push-unhealthy")
            if path == "/issues/12":
                return issue("push-unhealthy", 12)
            if path == "/pulls/25/files?per_page=100":
                return [{"filename": "test_push_monitor.py"}]
            raise AssertionError("unexpected API")
        self.assertEqual(q.check(token="test", pr_number=25, reader=reader),
                         "repair-evidence-present-tests-still-need-to-pass")
        self.assertEqual(calls, ["/pulls/25", "/issues/12", "/pulls/25/files?per_page=100"])

    def test_bad_auth_and_codes_never_read_other_paths(self):
        def unexpected(*args): raise AssertionError("network should not run")
        with self.assertRaises(ValueError):
            q.check(token=None, pr_number=2, reader=unexpected)
        self.assertEqual(q.CASE.findall("BOB-100-unknown-code"), [("100", "unknown-code")])


if __name__ == "__main__":
    unittest.main()
