import json
import os
import unittest
from unittest.mock import Mock, MagicMock, patch
import ai_peer_review_free as f


class FreeOidcReviewTests(unittest.TestCase):
    def test_unverified_free_plan_never_reads_github_or_calls_ai(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(f, "request_json") as call:
            with self.assertRaisesRegex(ValueError, "workers-free-unconfirmed"):
                f.main()
            call.assert_not_called()

    def test_github_oidc_needs_actions_environment(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "urllib.request.build_opener") as network:
            with self.assertRaisesRegex(ValueError, "oidc-runner-vars-missing"):
                f.github_oidc()
            network.assert_not_called()

    def test_oidc_rejects_wrong_destination_without_network(self):
        with patch.dict(os.environ, {
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://evil.example/token",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "test-only"}, clear=True), patch(
            "urllib.request.build_opener") as network:
            with self.assertRaisesRegex(ValueError, "oidc-host-rejected"):
                f.github_oidc()
            network.assert_not_called()

    def test_regional_github_oidc_endpoint_is_accepted(self):
        reply = Mock()
        reply.read.return_value = json.dumps({"value": "x"*130}).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = reply
        with patch.dict(os.environ, {
            "ACTIONS_ID_TOKEN_REQUEST_URL":
                "https://pipelinesghubeus7.actions.githubusercontent.com/_apis/token?api-version=2.0",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "temporary-gh-runner-only"}, clear=True), \
             patch("urllib.request.build_opener", return_value=opener):
            self.assertEqual(f.github_oidc(), "x"*130)
        req = opener.open.call_args.args[0]
        self.assertTrue(req.full_url.startswith("https://pipelinesghubeus7.actions.githubusercontent.com/"))
        self.assertIn("audience=", req.full_url)
        self.assertNotIn("temporary-gh-runner-only", req.full_url)

    def test_worker_request_is_fixed_and_requires_verified_response(self):
        response = Mock()
        response.read.return_value = json.dumps(
            {"ok": True, "response": "Kein eindeutig belegter Fehler."}).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch("urllib.request.build_opener", return_value=opener):
            answer = f.cloudflare_review("FILE: server.py\n+fixed()", 1, "a"*40, "test-jwt")
        self.assertEqual(answer, "Kein eindeutig belegter Fehler.")
        sent = opener.open.call_args.args[0]
        self.assertEqual(sent.full_url, f.WORKER)
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(sent.get_header("User-agent"), "curl/8.7.1")
        self.assertIn("Bearer test-jwt", sent.get_header("Authorization"))
        self.assertNotIn("test-jwt", sent.data.decode())

    def test_worker_oidc_reason_is_allowlisted_and_does_not_leak_raw_data(self):
        from urllib.error import HTTPError
        from io import BytesIO
        url = f.WORKER
        allowed = HTTPError(url, 401, "Unauthorized",
                            {"x-bob-oidc-check": "claim-workflow"}, BytesIO(b"secret"))
        with patch("urllib.request.build_opener") as network:
            network.return_value.open.side_effect = allowed
            with self.assertRaisesRegex(ValueError, "worker-oidc-claim-workflow"):
                f.cloudflare_review("FILE: a.py\n+fixed()", 1, "a" * 40, "dummy-jwt")
        untrusted = HTTPError(url, 401, "Unauthorized",
                              {"x-bob-oidc-check": "PRIVATE-BEARER"}, BytesIO(b"secret"))
        with patch("urllib.request.build_opener") as network:
            network.return_value.open.side_effect = untrusted
            with self.assertRaises(HTTPError):
                f.cloudflare_review("FILE: a.py\n+fixed()", 1, "a" * 40, "dummy-jwt")

    def test_invalid_worker_output_rejected(self):
        for invalid in [{}, {"ok": False, "response": "ignore"}, {"ok": True, "response": ""}]:
            reply = Mock()
            reply.read.return_value = json.dumps(invalid).encode()
            opener = MagicMock()
            opener.open.return_value.__enter__.return_value = reply
            with self.subTest(invalid=invalid), patch("urllib.request.build_opener", return_value=opener):
                with self.assertRaisesRegex(ValueError, "unavailable-review"):
                    f.cloudflare_review("FILE: server.py\n+fixed()", 1, "a"*40, "test-jwt")

    def test_bad_review_proposal_never_calls_worker(self):
        with patch("urllib.request.build_opener") as network:
            for diff in ["private", "FILE: a.py\n+line"]:
                with self.subTest(diff=diff), self.assertRaises(ValueError):
                    f.cloudflare_review(diff, 2, "invalid-sha", "jwt")
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
