import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import bob_issue_watchdog as watchdog


class WatchdogWorkflowStatusTests(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "ichrob/gold-dashboard1",
        },
        clear=True,
    )
    @patch.object(watchdog, "sync_issue", return_value="already-open")
    @patch.object(watchdog, "utc_now", return_value="2026-10-21T09:15:58+00:00")
    @patch.object(watchdog.time, "sleep")
    @patch.object(
        watchdog,
        "probe",
        side_effect=[
            ["product-leverage-clock-missing"],
            ["product-leverage-clock-missing"],
            ["product-leverage-clock-missing"],
        ],
    )
    def test_reported_finding_does_not_fail_successful_workflow(
        self, probe, sleep, utc_now, sync_issue
    ):
        mirror = SimpleNamespace(publish=Mock(return_value=1))
        with patch.dict(sys.modules, {"bob_problem_mirror": mirror}):
            with redirect_stdout(io.StringIO()) as output:
                result = watchdog.main()

        self.assertEqual(result, 0)
        self.assertEqual(probe.call_count, 3)
        sleep.assert_has_calls([call(15), call(120)])
        sync_issue.assert_called_once()
        mirror.publish.assert_called_once()
        self.assertIn(
            "codes=product-leverage-clock-missing", output.getvalue()
        )
        self.assertIn("issue=already-open", output.getvalue())


    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "ichrob/gold-dashboard1",
        },
        clear=True,
    )
    @patch.object(watchdog, "sync_issue", return_value="healthy")
    @patch.object(watchdog, "utc_now", return_value="2026-11-05T19:36:30+00:00")
    @patch.object(watchdog.time, "sleep")
    @patch.object(
        watchdog,
        "probe",
        side_effect=[
            ["product-quote-evidence-missing"],
            ["product-quote-evidence-missing"],
            [],
        ],
    )
    def test_product_gap_requires_delayed_third_confirmation(
        self, probe, sleep, utc_now, sync_issue
    ):
        mirror = SimpleNamespace(publish=Mock(return_value=0))
        with patch.dict(sys.modules, {"bob_problem_mirror": mirror}):
            result = watchdog.main()

        self.assertEqual(result, 0)
        self.assertEqual(probe.call_count, 3)
        sleep.assert_has_calls([call(15), call(120)])
        self.assertEqual(sync_issue.call_args.args[0], [])


    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "ichrob/gold-dashboard1",
        },
        clear=True,
    )
    @patch.object(watchdog, "sync_issue", return_value="healthy")
    @patch.object(watchdog, "utc_now", return_value="2026-11-05T19:36:30+00:00")
    @patch.object(watchdog.time, "sleep")
    @patch.object(
        watchdog,
        "probe",
        side_effect=[[], ["scanner-unreachable"]],
    )
    def test_new_fault_requires_two_matching_polls(
        self, probe, sleep, utc_now, sync_issue
    ):
        mirror = SimpleNamespace(publish=Mock(return_value=0))
        with patch.dict(sys.modules, {"bob_problem_mirror": mirror}):
            result = watchdog.main()

        self.assertEqual(result, 0)
        self.assertEqual(probe.call_count, 2)
        sleep.assert_called_once_with(15)
        self.assertEqual(sync_issue.call_args.args[0], [])


if __name__ == "__main__":
    unittest.main()
