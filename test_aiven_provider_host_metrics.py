import unittest
from datetime import datetime, timezone, timedelta

from aiven_provider_host_metrics import read

NOW = datetime(2026, 11, 14, 21, 5, tzinfo=timezone.utc)


def env(**values):
    return dict({"BOB_AIVEN_METRICS_ONCE": "1",
                 "BOB_AIVEN_METRICS_TOKEN": "temporary-fixture-not-real",
                 "BOB_AIVEN_METRICS_PROJECT": "bob-test",
                 "BOB_AIVEN_METRICS_SERVICE": "pg-free"}, **values)


def metrics(memory=35, disk=22, date="2026-11-14T21:04:00Z"):
    def chart(pct):
        return {"cols": [{"label": "Time", "type": "datetime"},
                         {"label": "Percentage", "type": "number"}],
                "rows": [{"c": [{"v": date}, {"v": pct}]}]}
    return {"metrics": {"mem_usage": chart(memory), "disk_usage": chart(disk)}}


class AivenProviderMetricsTests(unittest.TestCase):
    def test_disabled_and_missing_permissions_never_call_provider(self):
        called = []
        def fake(*args):
            called.append(True)
            raise AssertionError("should never fetch")
        self.assertEqual(read({}, fake)["status"], "disabled")
        self.assertEqual(read({"BOB_AIVEN_METRICS_ONCE": "1"}, fake)["status"],
                         "not-configured")
        self.assertEqual(called, [])

    def test_valid_read_only_api_request(self):
        called = []
        def fake(url, headers, body):
            called.append((url, headers, body))
            return metrics()
        output = read(env(), fake, NOW)
        self.assertEqual(output["status"], "observed")
        self.assertEqual(output["host"]["source"], "aiven-service-metrics-api")
        self.assertEqual(output["host"]["node"], "service-wide")
        self.assertEqual(output["host"]["memoryUsedPct"], 35.0)
        self.assertEqual(output["host"]["diskUsedPct"], 22.0)
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0][0],
                         "https://api.aiven.io/v1/project/bob-test/service/pg-free/metrics")
        self.assertEqual(called[0][2], b'{"period":"hour"}')
        self.assertTrue(called[0][1]["Authorization"].startswith("aivenv1 "))

    def test_not_authorized_or_server_failure_redacted(self):
        def fail(*_args):
            raise RuntimeError("secret TOKEN exposure at https://api.aiven.io")
        result = read(env(), fail, NOW)
        self.assertEqual(result["status"], "provider-metrics-unavailable")
        self.assertNotIn("TOKEN", str(result))
        self.assertNotIn("bob-test", str(result))

    def test_no_external_host_or_redirect_name_in_endpoint(self):
        bad = read(env(BOB_AIVEN_METRICS_SERVICE="pg-free/../evil"),
                   lambda *_: metrics(), NOW)
        self.assertEqual(bad["status"], "not-configured")

    def test_outdated_samples_never_unlock_gate(self):
        result = read(env(), lambda *_: metrics(date="2026-11-14T20:10:00Z"), NOW)
        self.assertEqual(result["status"], "metrics-stale-or-future")

    def test_future_samples_never_unlock_gate(self):
        result = read(env(), lambda *_: metrics(date="2026-11-14T21:06:00Z"), NOW)
        self.assertEqual(result["status"], "metrics-stale-or-future")

    def test_unknown_or_incomplete_charts_fail_closed(self):
        self.assertEqual(read(env(), lambda *_: {"metrics": {}}, NOW)["status"],
                         "schema-or-metrics-unverified")
        self.assertEqual(read(env(), lambda *_: {"metrics": {
            "mem_usage": metrics()["metrics"]["mem_usage"]}}, NOW)["status"],
            "schema-or-metrics-unverified")

    def test_fractional_unknown_units_rejected(self):
        result = read(env(), lambda *_: metrics(memory=0.25), NOW)
        self.assertEqual(result["status"], "schema-or-metrics-unverified")

    def test_json_google_date_parses_as_utc(self):
        sample = metrics(date="Date(2026,10,14,21,4,0)")
        result = read(env(), lambda *_: sample, NOW)
        self.assertEqual(result["status"], "observed")

    def test_metrics_must_be_time_aligned(self):
        sample = metrics()
        sample["metrics"]["disk_usage"]["rows"][0]["c"][0]["v"] = (
            "2026-11-14T20:55:00Z")
        result = read(env(), lambda *_: sample, NOW)
        self.assertEqual(result["status"], "schema-or-metrics-unverified")

    def test_negative_and_over_limit_are_untrusted(self):
        for value in (-2, 101, float("nan"), None):
            result = read(env(), lambda *_: metrics(memory=value), NOW)
            self.assertEqual(result["status"], "schema-or-metrics-unverified")


if __name__ == "__main__":
    unittest.main()
