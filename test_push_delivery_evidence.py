"""Web Push audit must not turn tests into market evidence or leak subscriptions."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import push_server


class PushDeliveryEvidenceTests(unittest.TestCase):
    def test_live_early_warning_provider_attempt_is_not_a_handset_receipt(self):
        message = {
            "title": "FRÜHWARNUNG · LONG",
            "body": "PRIVATE BODY",
            "data": {
                "eventKind": "early-warning", "events": ["early-warning"],
                "direction": "LONG", "signalBarAt": 1792789200000,
                "dataAt": 1792789220000, "test": False,
                "traceId": "a" * 32, "decisionId": "b" * 32,
                "token": "DO-NOT-STORE",
            },
        }
        with patch.object(push_server, "_webpush", return_value=SimpleNamespace(status_code=201)), \
             patch.object(push_server.diagnostic_history, "emit") as emit:
            push_server.webpush(data=json.dumps(message),
                subscription_info={"endpoint": "PRIVATE ENDPOINT"})
        emit.assert_called_once()
        stage, trace, payload, decision = emit.call_args.args
        self.assertEqual((stage, trace, decision),
                         ("push-delivery", "a" * 32, "b" * 32))
        self.assertEqual(payload["outcome"], "provider-accepted")
        self.assertEqual(payload["direction"], "LONG")
        self.assertEqual(payload["eventKinds"], ["early-warning"])
        self.assertIs(payload["test"], False)
        self.assertNotIn("body", payload)
        self.assertNotIn("PRIVATE", str(payload))
        self.assertNotIn("token", payload)
        self.assertNotIn("endpoint", payload)

    def test_synthetic_warning_never_classified_as_non_test(self):
        message = push_server.early_warning_test_message("SHORT", 1792789200000)
        with patch.object(push_server, "_webpush", return_value=SimpleNamespace(status_code=201)), \
             patch.object(push_server.diagnostic_history, "emit") as emit:
            push_server.webpush(data=json.dumps(message),
                subscription_info={"endpoint": "PRIVATE ENDPOINT"})
        payload = emit.call_args.args[2]
        self.assertEqual(payload["eventKinds"], ["early-warning-test"])
        self.assertEqual(payload["direction"], "SHORT")
        self.assertIs(payload["test"], True)
        self.assertIs(payload["synthetic"], True)
        self.assertIsNone(payload["signalBarAt"])

    def test_rejected_provider_attempt_remains_a_failed_attempt(self):
        message = {"title": "X", "data": {"eventKind": "signal-change"}}
        with patch.object(push_server, "_webpush",
                          side_effect=push_server.WebPushException("rejected")), \
             patch.object(push_server.diagnostic_history, "emit") as emit:
            with self.assertRaises(push_server.WebPushException):
                push_server.webpush(data=json.dumps(message),
                    subscription_info={"endpoint": "PRIVATE ENDPOINT"})
        payload = emit.call_args.args[2]
        self.assertEqual(payload["outcome"], "provider-rejected")
        self.assertIsNone(payload["direction"])
        self.assertIsNone(payload["httpStatus"])


if __name__ == "__main__":
    unittest.main()
