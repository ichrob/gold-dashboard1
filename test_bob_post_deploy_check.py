"""Fail-closed scheduled post-deploy status; no external calls."""
import unittest
import os
import tempfile
import io
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tools.bob_post_deploy_check import classify, read_ci_evidence

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

    def test_ci_evidence_request_is_bounded_below_response_cap(self):
        calls = []
        responses = [
            {"object": {"sha": SHA}},
            {"workflow_runs": run()},
        ]

        def fake_github_json(path):
            calls.append(path)
            return responses.pop(0)

        with patch("tools.bob_post_deploy_check.github_json", side_effect=fake_github_json):
            self.assertEqual(read_ci_evidence(), (SHA, run()))
        self.assertEqual(calls, [
            "/git/ref/heads/main",
            "/actions/workflows/ci.yml/runs?branch=main&event=push&per_page=5",
        ])

    def test_finished_failed_ci_never_becomes_pending_in_grace_period(self):
        a, b = self.healthy()
        self.assertEqual(classify(SHA, run(conclusion="failure", elapsed=1), a, b, NOW)["state"], "failed")

    def test_actions_pending_is_explicit_and_never_runs_deployed_regressions(self):
        import tools.bob_post_deploy_check as check
        for state, cli_exit, action_exit in (("verified",0,0),("pending",2,0),("failed",1,1)):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/"output"
                summary = Path(directory)/"summary"
                with patch.object(check, "read_ci_evidence", return_value=(SHA, run())), \
                     patch.object(check, "read_health", return_value={}), \
                     patch.object(check, "classify", return_value={"state":state,"reason":"fixture"}), \
                     patch.dict(os.environ, {"GITHUB_OUTPUT":str(output), "GITHUB_STEP_SUMMARY":str(summary)}), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(check.run(), cli_exit)
                    self.assertFalse(output.exists())
                    self.assertEqual(check.run(github_actions=True), action_exit)
                self.assertEqual(output.read_text(), "state="+state+"\n")
                self.assertIn("Status: **"+state+"**", summary.read_text())
        yml=(Path(__file__).resolve().parent/".github/workflows/bob-post-deploy-verification.yml").read_text()
        self.assertIn("id: observation", yml)
        self.assertEqual(yml.count("if: steps.observation.outputs.state == 'verified'"), 2)
        self.assertNotIn("continue-on-error", yml)

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
