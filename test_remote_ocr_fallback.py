"""No cloud calls: prove the opt-in OCR transport fails closed."""
import base64
import hashlib
import json
import os
import unittest
from unittest.mock import Mock, patch

import remote_ocr_fallback as remote


IMAGE = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"synthetic" * 30).decode()
TOKEN = "x" * 48
URL = "https://bob-ocr-test-123-europe-west3.a.run.app/ocr"


class FakeResponse:
    status = 200
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, count):
        return self.body[:count]


class RemoteOcrTests(unittest.TestCase):
    def settings(self, **kwargs):
        params = dict(BOB_REMOTE_OCR_ENABLED="true",
                      BOB_REMOTE_OCR_URL=URL, BOB_REMOTE_OCR_TOKEN=TOKEN)
        params.update(kwargs)
        return patch.dict(os.environ, params, clear=True)

    def test_default_off_does_not_attempt_any_connection(self):
        opener = Mock()
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(remote.recognize({"png": IMAGE}, opener=opener))
        opener.open.assert_not_called()

    def test_invalid_host_or_absent_secret_fails_closed(self):
        for url in ("http://bob-ocr.a.run.app/ocr",
                    "https://evil.example/ocr",
                    "https://bob-ocr.a.run.app.evil.example/ocr",
                    "https://bob-ocr.a.run.app/redirect",
                    "https://bob-ocr.a.run.app/ocr?token=unsafe"):
            with self.settings(BOB_REMOTE_OCR_URL=url):
                with self.assertRaises(remote.RemoteOcrError):
                    remote.recognize({"png": IMAGE}, opener=Mock())
        with self.settings(BOB_REMOTE_OCR_TOKEN="short"):
            with self.assertRaises(remote.RemoteOcrError):
                remote.recognize({"png": IMAGE}, opener=Mock())

    def test_missing_iam_identity_never_sends_private_screenshot(self):
        opener = Mock()
        with self.settings(), self.assertRaises(remote.RemoteOcrError):
            remote.recognize({"png": IMAGE}, opener=opener)
        opener.open.assert_not_called()

    def test_redirect_is_forbidden_even_with_authentication(self):
        with self.assertRaises(remote.RemoteOcrError):
            remote._NoRedirect().redirect_request(None,None,302,"redirect",{},"https://evil.example/ocr")

    def test_correlation_and_exact_pass_count(self):
        digest = hashlib.sha256(base64.b64decode(IMAGE)).hexdigest()
        body = json.dumps({"sha256": digest, "passes": ["one", "two", "three"]}).encode()
        opener = Mock()
        opener.open.return_value = FakeResponse(body)
        with self.settings(), patch.object(remote, '_fetch_identity_token', return_value='signed-id-token'):
            self.assertEqual(remote.recognize({"png": IMAGE}, opener=opener),
                             [["one", "two", "three"]])
        request = opener.open.call_args.args[0]
        sent = json.loads(request.data)
        self.assertEqual(sent["sha256"], digest)
        self.assertEqual(sent["png"], IMAGE)
        self.assertEqual(request.get_header("Authorization"), "Bearer signed-id-token")
        self.assertEqual(request.get_header("X-bob-ocr-key"), TOKEN)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 70)

    def test_rejects_corrupt_cross_image_or_single_pass_results(self):
        bad_responses = [
            {"sha256": "0" * 64, "passes": ["one", "two"]},
            {"sha256": hashlib.sha256(base64.b64decode(IMAGE)).hexdigest(),
             "passes": ["one"]},
            {"sha256": hashlib.sha256(base64.b64decode(IMAGE)).hexdigest(),
             "passes": ["one", "two"], "approved": True},
        ]
        for payload in bad_responses:
            opener = Mock()
            opener.open.return_value = FakeResponse(json.dumps(payload).encode())
            with self.settings(), patch.object(remote, '_fetch_identity_token', return_value='signed-id-token'), self.assertRaises(remote.RemoteOcrError):
                remote.recognize({"png": IMAGE}, opener=opener)

    def test_provider_failure_never_returns_fake_text(self):
        opener = Mock()
        opener.open.side_effect = TimeoutError("external provider failed")
        with self.settings(), patch.object(remote, '_fetch_identity_token', return_value='signed-id-token'), self.assertRaises(remote.RemoteOcrError):
            remote.recognize({"png": IMAGE}, opener=opener)


if __name__ == "__main__":
    unittest.main()
