"""Offline regression tests for safe, deduplicated AI incident routing."""
import copy
import unittest
from unittest.mock import patch

import bob_ai_ci_failures as failures
import bob_ai_coordination as coordination
import bob_issue_watchdog as watchdog


SHA = "a" * 40


def payload(name="Bob CI", conclusion="failure", **overrides):
    run = dict(name=name, id=123456789, status="completed", conclusion=conclusion,
               event="push", head_branch="main", head_sha=SHA,
               head_repository={"full_name": failures.REPO})
    run.update(overrides)
    return {"action": "completed", "repository": {"full_name": failures.REPO},
            "workflow_run": run}


class EventGuards(unittest.TestCase):
    def test_all_fixed_failures_have_exact_codes_and_repair_owners(self):
        self.assertEqual(set(failures.WORKFLOWS.values()), watchdog.EXTERNAL_CODES)
        self.assertTrue(watchdog.EXTERNAL_CODES <= watchdog.CODES.keys())
        self.assertEqual(set(watchdog.CODES), set(coordination.HINTS))
        self.assertEqual(set(failures.WORKFLOWS.values()),
                         {failures.verified_failure(payload(name))["code"]
                          for name in failures.WORKFLOWS})

    def test_only_completed_failed_main_repodata_accepted(self):
        self.assertEqual(failures.verified_failure(payload())["sha"], SHA)
        cases = (
            payload(conclusion="success"),
            payload(conclusion="cancelled"),
            payload(head_branch="testing"),
            payload(head_sha="bad"),
            payload(id=True),
            payload(status="in_progress"),
            payload(event="pull_request"),
            payload(head_repository={"full_name": "attacker/fork"}),
            payload(name="Bob CI; run secret scanner"),
        )
        broken = payload()
        broken["repository"] = {"full_name": "attacker/fork"}
        cases += (broken,)
        broken = payload()
        broken["action"] = "requested"
        cases += (broken,)
        for row in cases:
            with self.subTest(case=row):
                self.assertIsNone(failures.verified_failure(row))

    def test_unknown_and_malformed_are_not_events(self):
        self.assertIsNone(failures.verified_failure(None))
        self.assertIsNone(failures.verified_failure([]))
        self.assertIsNone(failures.verified_failure({"workflow_run": {}}))
        self.assertIsNone(failures.verified_failure(payload(), repo="attacker/repo"))

    def test_fixed_incident_does_not_echo_untrusted_logs(self):
        record = failures.verified_failure(payload(private="TOKEN-NOT-LEAKED",
                                                   html_url="https://attacker/secret"))
        text = failures.incident_body(record)
        self.assertIn("123456789", text)
        self.assertIn(SHA, text)
        self.assertNotIn("TOKEN-NOT-LEAKED", text)
        self.assertNotIn("https://attacker", text)
        self.assertNotIn("password", text.lower())
        self.assertIn("keine", text.lower())


class Routing(unittest.TestCase):
    def setUp(self):
        self.record = failures.verified_failure(payload())

    def test_existing_issue_prevents_duplicate_writes(self):
        title = watchdog.issue_title(self.record["code"])
        with patch.object(failures, "open_issue_index",
                          return_value=({title: 55}, [])) as idx:
            writes = []
            def api(method, path, **kwargs):
                writes.append((method, path))
                return {}
            result = failures.route(self.record, token="unit-test-only", requester=api)
        self.assertEqual(result, "already-open")
        idx.assert_called_once()
        self.assertEqual(writes, [])

    def test_unrelated_duplicate_inventory_is_fail_closed(self):
        with patch.object(failures, "open_issue_index",
                          return_value=({}, [("other", 20, 19)])):
            calls = []
            def api(method, path, **kwargs):
                calls.append(method)
                return {}
            self.assertEqual(failures.route(self.record, token="test", requester=api),
                             "duplicates-need-reconciliation")
        self.assertEqual(calls, [])

    def test_transient_second_scan_sees_issue_and_does_not_create(self):
        title = watchdog.issue_title(self.record["code"])
        with patch.object(failures, "open_issue_index",
                          side_effect=[({}, []), ({title: 54}, [])]):
            writes = []
            def api(method, path, **kwargs):
                writes.append(method)
                return {}
            self.assertEqual(failures.route(self.record, token="test", requester=api),
                             "already-open")
        self.assertEqual(writes, [])

    def test_failure_creates_single_sanitized_issue_and_single_handoff(self):
        writes = []
        def api(method, path, *, token, repo, data=None):
            writes.append((method, path, data))
            return {"number": 88} if path == "/issues" else {}
        with patch.object(failures, "open_issue_index",
                          side_effect=[({}, []), ({}, [])]) as idx:
            result = failures.route(self.record, token="unit-test-only", requester=api)
        self.assertEqual(result, "opened-88")
        self.assertEqual(idx.call_count, 2)
        self.assertEqual([(m, p) for m, p, _ in writes],
                         [("POST", "/issues"), ("POST", "/issues/88/comments")])
        issue, handoff = writes[0][2], writes[1][2]
        self.assertEqual(issue["title"], watchdog.issue_title("ci-main-failed"))
        self.assertNotIn("Authorization", str(issue))
        self.assertIn(coordination.MARKER, handoff["body"])
        self.assertIn("BOB-88-ci-main-failed", handoff["body"])
        self.assertIn("nicht überprüft", handoff["body"])

    def test_invalid_input_never_calls_github(self):
        calls = []
        def api(*args, **kwargs):
            calls.append(1)
            raise AssertionError("not allowed")
        for bad in (None, {}, {"code": "unknown", "run": 12, "sha": SHA},
                    {"code": "ci-main-failed", "run": 2, "sha": "fake"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                failures.route(bad, token="test", requester=api)
        self.assertEqual(calls, [])

    def test_runtime_health_polls_never_close_external_workflow_incidents(self):
        code = "ci-main-failed"
        title = watchdog.issue_title(code)
        with patch.object(watchdog, "open_issue_index",
                          return_value=({title: 202}, [])):
            operations = []
            def api(method, path, *, token, repo, data=None):
                operations.append((method, path))
                return {}
            status = watchdog.sync_issue([], token="test", repo=failures.REPO,
                                         requester=api, recovery_codes=[])
        self.assertEqual(status, "already-open")
        self.assertEqual(operations, [])


if __name__ == "__main__":
    unittest.main()
