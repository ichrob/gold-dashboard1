import os
import unittest
from unittest.mock import patch

import ai_peer_review as peer


class SecondAI(unittest.TestCase):
    def test_no_billing_attestation_blocks_all_calls(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(peer, "request_json") as send:
                with self.assertRaisesRegex(ValueError, "free-account-unconfirmed"):
                    peer.main()
                send.assert_not_called()

    def test_no_api_credentials_or_valid_pr_blocks_all_calls(self):
        with patch.dict(os.environ, {"BOB_AI_FREE_ONLY": "confirmed-workers-free"}, clear=True):
            with patch.object(peer, "request_json") as send:
                with self.assertRaisesRegex(ValueError, "missing-config"):
                    peer.main()
                send.assert_not_called()

    def test_secret_or_non_source_diffs_rejected(self):
        for item in [
            {"filename": "server.py", "patch": "+api_key = 'sensitive'"},
            {"filename": "server.py", "patch": "+Authorization: Bearer test"},
            {"filename": ".env", "patch": "+VAR=not-public"},
        ]:
            with self.subTest(item=item), self.assertRaisesRegex(ValueError, "no-safe"):
                peer.safe_files([item])

    def test_bounded_public_patch(self):
        diff = peer.safe_files([{"filename": "server.py", "patch": "@@ -1 +1 @@\n-old()\n+new()"}])
        self.assertIn("server.py", diff)
        self.assertIn("+new()", diff)
        with self.assertRaisesRegex(ValueError, "no-safe"):
            peer.safe_files([{"filename": "server.py", "patch": "a" * 4501}])

    def test_invalid_cloudflare_responses_never_publish(self):
        for data in [{"success": False}, {"success": True, "result": {"response": ""}}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                peer.review_response(data)
        out = peer.review_response({"success": True, "result": {"response": "See https://bad.example"}})
        self.assertNotIn("https://", out)

    def test_prompt_never_supplies_tools_or_order_actions(self):
        prompt = peer.provider_payload("FILE: x.py\n+pass")
        self.assertEqual(len(prompt["messages"]), 2)
        self.assertNotIn("tools", prompt)
        self.assertEqual(prompt["max_tokens"], 1200)


if __name__ == "__main__":
    unittest.main()
