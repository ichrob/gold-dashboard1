"""Fail-closed scheduled post-deploy status; no external calls."""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tools.bob_post_deploy_check import classify

SHA = "a" * 40
OLD = "b" * 40
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def run(status="completed", conclusion="success", elapsed=60):
    instant = (NOW - timedelta(seconds=elapsed)).isoformat()
    return [{"head_sha": SHA, "event": "push", "name": "Bob CI",
             "status": status, "conclusion": conclusion,
             "created_at": instant, "updated_at": instant}]


class DeployClassificationTests(unittest.TestCase):
    def healthy(self):
        return {"status": "ok", "build": SHA}, {"ok": True, "build": SHA}

    def test_verified_requires_exact_main_sha_ci_and_both_services(self):
        a, b = self.healthy()
        self.assertEqual(classify(SHA, run(), a, b, NOW)["state"], "verified")
        self.assertEqual(classify(OLD, run(), a, b, NOW)["state"], "failed")

    def test_stale_render_commit_is_pending_then_failed(self):
        a, b = self.healthy()
        a["build"] = OLD
        self.assertEqual(classify(SHA, run(elapsed=60), a, b, NOW)["state"], "pending")
        self.assertEqual(classify(SHA, run(elapsed=3600), a, b, NOW)["state"], "failed")

    def test_unavailable_push_is_never_success(self):
        a, _ = self.healthy()
        self.assertEqual(classify(SHA, run(elapsed=3600), a, None, NOW)["state"], "failed")

    def test_no_ci_failure_unknown_ci_and_future_time_fail_closed(self):
        a, b = self.healthy()
        self.assertEqual(classify(SHA, [], a, b, NOW)["state"], "failed")
        self.assertEqual(classify(SHA, run(conclusion="failure", elapsed=3600), a, b, NOW)["state"], "failed")
        self.assertEqual(classify(SHA, run(elapsed=-3600), a, b, NOW)["state"], "failed")
        self.assertEqual(classify("short", run(), a, b, NOW)["state"], "failed")

    def test_running_ci_is_pending_only_within_bounded_period(self):
        a, b = self.healthy()
        self.assertEqual(classify(SHA, run(status="in_progress", conclusion=None), a, b, NOW)["state"], "pending")
        self.assertEqual(classify(SHA, run(status="in_progress", conclusion=None, elapsed=3600), a, b, NOW)["state"], "failed")

    def test_no_push_trigger_or_broker_access_in_separate_workflow(self):
        yml=(Path(__file__).resolve().parent/".github/workflows/bob-post-deploy-verification.yml").read_text()
        self.assertIn("workflow_dispatch:", yml)
        self.assertIn("schedule:", yml)
        self.assertNotIn("\n  push:", yml)
        self.assertNotIn("\n  workflow_run:", yml)
        self.assertIn("python -m tools.bob_post_deploy_check", yml)
        self.assertNotIn("secrets.PUSH_SERVICE_TOKEN", yml)


if __name__ == "__main__":
    unittest.main()
