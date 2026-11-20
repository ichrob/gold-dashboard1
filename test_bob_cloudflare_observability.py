"""Offline regression of Bob's no-cost Cloudflare central reporting policy."""
import unittest
from bob_cloudflare_observability import (
    WORKERS, FREE_INGESTION_LIMIT_BYTES, central_digest,
    summarize_issues, summarize_settings, summarize_usage,
    summarize_cron_receipts, CRON_CADENCE_SECONDS,
)


class TestCloudflareCentral(unittest.TestCase):
    def setUp(self):
        self.settings = {
            name: {"success": True, "result": {"observability": {
                "enabled": True, "logs": {"enabled": True},
                "issues": {"enabled": True},
            }}}
            for name in WORKERS
        }
        self.usage = {"success": True, "result": {
            "events": 3,
            "breakdown": [
                {"service": WORKERS[0], "count": 2, "eventSize": 2400},
                {"service": "evil\nAuthorization: Bearer 123", "count": 1, "eventSize": 100},
            ],
        }}
        self.issues = {"success": True, "result": {
            "activeIssues": 0, "activeOccurrences": 0,
            "lastIssue": {"title": "SECRET not for publication"},
        }}

    def test_no_secrets_or_unknown_service_names(self):
        digest = central_digest(self.usage, self.issues, self.settings)
        serial = repr(digest)
        self.assertNotIn("evil", serial)
        self.assertNotIn("Bearer", serial)
        self.assertNotIn("SECRET", serial)
        self.assertEqual(digest["usage"]["bytes"], 2500)
        self.assertEqual(digest["usage"]["otherEvents"], 1)
        self.assertTrue(digest["allWorkersObservable"])
        self.assertIsNone(digest["healthy"])
        self.assertFalse(digest["costAuthorized"])
        self.assertFalse(digest["newPushChannel"])

    def test_missing_logs_remain_unknown_not_healthy(self):
        settings = dict(self.settings)
        settings[WORKERS[2]] = {"success": True, "result": {"observability": None}}
        digest = central_digest(self.usage, self.issues, settings)
        self.assertEqual(digest["coverage"][WORKERS[2]]["logs"], "unknown")
        self.assertFalse(digest["allWorkersObservable"])
        self.assertEqual(digest["issues"]["active"], 0)
        self.assertIsNone(digest["healthy"])

    def test_partial_usage_is_unknown(self):
        self.usage["result"]["events"] = 8
        result = summarize_usage(self.usage)
        self.assertEqual(result["state"], "unknown")
        self.assertIn("partial_usage_breakdown", result["warnings"])

    def test_bad_or_huge_payload_fails_closed(self):
        self.usage["result"]["breakdown"][0]["eventSize"] = -1
        self.assertEqual(summarize_usage(self.usage)["state"], "unknown")
        self.assertEqual(summarize_usage({"success": False})["state"], "unknown")
        self.assertEqual(summarize_issues({"success": True, "result": {"activeIssues": True}})["state"], "unknown")

    def test_budget_warning_is_advisory(self):
        self.usage["result"]["breakdown"][0]["eventSize"] = 410_000_000
        result = summarize_usage(self.usage)
        self.assertIn("high_observed_ingestion_check_free_plan", result["warnings"])
        self.assertGreater(FREE_INGESTION_LIMIT_BYTES, result["bytes"])
        self.assertFalse(central_digest(self.usage, self.issues, self.settings)["costAuthorized"])

    def test_empty_result_is_not_an_outage_or_recovery(self):
        usage = {"success": True, "result": {"events": 0, "breakdown": []}}
        digest = central_digest(usage, self.issues, {})
        self.assertEqual(digest["usage"]["state"], "observed")
        self.assertEqual(digest["usage"]["events"], 0)
        self.assertIsNone(digest["healthy"])
        self.assertFalse(digest["allWorkersObservable"])

    def test_actual_cloudflare_cron_receipts_only(self):
        now = 1795181040
        cron = {"success": True, "result": {"calculations": [{
            "alias": "lastScheduledEpochSeconds",
            "aggregates": [
                {"groupKey": "bob-watchdog-clock", "value": now - 500},
                {"groupKey": "bob-oracle-a1-retry", "value": now - 1200.25},
                {"groupKey": "other-private-worker", "value": now},
            ],
        }]}}
        result = summarize_cron_receipts(cron, now_epoch_seconds=now)
        self.assertEqual(result["state"], "observed")
        self.assertTrue(result["allRecentlyObserved"])
        self.assertEqual(result["workers"]["bob-watchdog-clock"]["state"], "recent")
        self.assertEqual(result["workers"]["bob-oracle-a1-retry"]["lastScheduledAt"],
                         int(now - 1200.25))
        self.assertNotIn("other-private-worker", repr(result))
        self.assertEqual(len(result["workers"]), len(CRON_CADENCE_SECONDS))

    def test_cron_receipts_never_infer_success(self):
        now = 1795181040
        cron = {"success": True, "result": {"calculations": [{
            "alias": "lastScheduledEpochSeconds",
            "aggregates": [
                {"groupKey": "bob-watchdog-clock", "value": now - 3700},
            ],
        }]}}
        digest = central_digest(self.usage, self.issues, self.settings,
                                cron=cron, now_epoch_seconds=now)
        self.assertEqual(digest["cronReceipts"]["workers"]["bob-watchdog-clock"]["state"],
                         "old-observation")
        self.assertEqual(digest["cronReceipts"]["workers"]["bob-oracle-a1-retry"]["state"],
                         "not-observed")
        self.assertFalse(digest["cronReceipts"]["allRecentlyObserved"])
        self.assertIsNone(digest["healthy"])
        self.assertFalse(digest["newPushChannel"])

    def test_malformed_cron_results_fail_closed(self):
        now = 1795181040
        base = {"success": True, "result": {"calculations": [{
            "alias": "lastScheduledEpochSeconds",
            "aggregates": [{"groupKey": "bob-oracle-a1-retry", "value": now + 1000}],
        }]}}
        self.assertEqual(summarize_cron_receipts(base, now_epoch_seconds=now)["state"],
                         "unknown")
        base["result"]["calculations"][0]["aggregates"][0]["value"] = float("nan")
        self.assertEqual(summarize_cron_receipts(base, now_epoch_seconds=now)["state"],
                         "unknown")
        self.assertEqual(summarize_cron_receipts({"success": False}, now_epoch_seconds=now)["state"],
                         "unknown")
        self.assertEqual(summarize_cron_receipts(base, now_epoch_seconds=None)["state"],
                         "unknown")


if __name__ == "__main__":
    unittest.main()
