"""Privacy and classification tests for bounded push delivery evidence."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
import push_delivery_history as history


class PushHistoryTests(unittest.TestCase):
    def test_default_window_and_boundaries(self):
        now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
        result = history.arguments({}, now=now)
        self.assertEqual(result["start"], "2026-10-23T10:00:00+00:00")
        self.assertEqual(result["end"], "2026-10-24T10:00:00+00:00")
        for bad in (
            {"start": "2026-10-23T10:00:00", "end": "2026-10-24T10:00:00Z"},
            {"start": "2026-10-22T10:00:00Z", "end": "2026-10-24T10:00:00Z"},
            {"offset": -1}, {"offset": True}, {"unknown": 1},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                history.arguments(bad, now=now)

    def test_test_not_mistaken_for_market_and_no_secrets(self):
        conn = Mock()
        at = datetime(2026, 10, 23, 19, tzinfo=timezone.utc)
        conn.execute.return_value.fetchall.return_value = [
            ("first", at, {
                "outcome": "provider-accepted", "eventKinds": ["early-warning-test"],
                "direction": "LONG", "test": True, "synthetic": True,
                "secret": "NEVER EXPOSE", "endpoint": "private"}),
            ("second", at, {
                "outcome": "provider-accepted", "eventKinds": ["early-warning"],
                "direction": "LONG", "test": False, "synthetic": False,
                "signalBarAt": 123, "dataAt": 456,
                "token": "NEVER EXPOSE"}),
        ]
        report = history.report(conn)
        first, second = report["records"]
        self.assertEqual(first["classification"], "synthetic-test")
        self.assertEqual(second["classification"], "not-marked-test")
        self.assertIs(second["marketEventVerified"], False)
        self.assertEqual(first["handsetReceipt"], "not-verified")
        self.assertNotIn("secret", str(report))
        self.assertNotIn("NEVER EXPOSE", str(report))
        self.assertEqual(conn.execute.call_args.args[1][2:], (101, 0))


if __name__ == "__main__":
    unittest.main()
