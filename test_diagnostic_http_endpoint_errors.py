"""Goal 15: specific assertions, not a live Render acceptance."""
import json
import unittest

from diagnostic_http_endpoint_errors import classify

A = "2026-10-25T10:00:00Z"
B = "2026-10-25T11:00:00Z"


def row(code, path="/health", at="2026-10-25T10:15:00Z", **extra):
    return {"type": "request", "statusCode": code, "path": path,
            "timestamp": at, **extra}


def sample(records, **extra):
    return classify(records, service="bob-private-scanner",
                    window_start=A, window_end=B, **extra)


class DiagnosticHttpErrorsTests(unittest.TestCase):
    def test_endpoint_5xx_is_separate_from_4xx(self):
        result = sample([row("200"), row(401), row("503", "/api/live"),
                         row(404, "/api/live")])
        self.assertEqual(result["httpClasses"]["2xx"], 1)
        self.assertEqual(result["httpClasses"]["4xx"], 2)
        self.assertEqual(result["httpClasses"]["5xx"], 1)
        mapped = {entry["endpoint"]: entry for entry in result["endpoints"]}
        self.assertEqual(mapped["/api/live"]["serverErrors"], 1)
        self.assertEqual(mapped["/health"]["accessDenied"], 1)
        self.assertFalse(result["completeTrafficProven"])
        self.assertFalse(result["liveVerified"])

    def test_secret_path_user_ids_and_queries_cannot_leak(self):
        result = sample([row(500, "/api/user/robert?access_token=SECRET-KEY"),
                         row(403, "/health?key=PRIVATE"),
                         row(503, "https://victim/private?t=BAD")])
        txt = json.dumps(result)
        for secret in ("robert", "SECRET-KEY", "PRIVATE", "victim", "BAD"):
            self.assertNotIn(secret, txt)
        self.assertIn("other-unclassified", txt)
        self.assertIn("/health", txt)
        self.assertFalse(result["realOrders"])

    def test_render_application_http_log_lines(self):
        rows = [
            {"timestamp": "2026-10-25T10:15:00Z",
             "message": "BOB_HTTP path=/api/live?q=redacted method=GET status=503 rndr_id=123"},
            {"timestamp": "2026-10-25T10:16:00Z",
             "message": "BOB_PUSH_HTTP method=HEAD path=/health status=200"},
            {"timestamp": "2026-10-25T10:17:00Z",
             "message": "unrecognized status=200 path=/health"},
        ]
        result = sample(rows, has_more=True)
        self.assertEqual(result["validRequestRecords"], 2)
        self.assertEqual(result["httpClasses"]["5xx"], 1)
        self.assertEqual(result["httpClasses"]["2xx"], 1)
        self.assertEqual(result["invalidOrIgnoredRecords"], 1)
        self.assertTrue(result["sampleTruncated"])
        self.assertNotIn("redacted", json.dumps(result))

    def test_empty_and_invalid_inputs_fail_closed(self):
        for records in ([], [row(200, at="not-a-timestamp")],
                        [row(True)], [row(600)], [row("500\n")]):
            self.assertEqual(sample(records)["status"], "insufficient-evidence")
        self.assertEqual(classify([], service="not-your-service",
                         window_start=A, window_end=B)["status"], "insufficient-evidence")
        self.assertEqual(classify([], service="bob-push-service",
                         window_start=B, window_end=A)["status"], "insufficient-evidence")

    def test_bounded_and_paged_samples_do_not_claim_full_coverage(self):
        result = sample([row(200)] * 300, has_more=True)
        self.assertEqual(result["sampledRecords"], 250)
        self.assertEqual(result["validRequestRecords"], 250)
        self.assertTrue(result["sampleTruncated"])
        self.assertFalse(result["completeTrafficProven"])

    def test_wrong_window_and_non_request_not_counted(self):
        result = sample([row(200, at="2026-10-25T12:00:00Z"),
                         row(503, type="app"), row(200)])
        self.assertEqual(result["validRequestRecords"], 1)
        self.assertEqual(result["invalidOrIgnoredRecords"], 2)
        self.assertEqual(result["httpClasses"]["5xx"], 0)
        self.assertEqual(result["httpClasses"]["2xx"], 1)


if __name__ == "__main__":
    unittest.main()
