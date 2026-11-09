"""Oracle OCR transport contracts: all images synthetic, no network calls."""
import base64
import hashlib
import json
import os
import unittest
from unittest.mock import Mock, patch
import remote_ocr_fallback as remote


IMAGE = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"synthetic" * 30).decode()
TOKEN = "x" * 48
ADDRESS = "9.9.9.9"   # Only in mocked tests. Never contacted.
URL = "https://" + ADDRESS + ":8443/ocr"
CA = "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----"


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
        values = dict(
            BOB_REMOTE_OCR_ENABLED="true",
            BOB_REMOTE_OCR_COST_POLICY="oci_always_free_verified",
            BOB_REMOTE_OCR_URL=URL,
            BOB_REMOTE_OCR_ALLOWED_IP=ADDRESS,
            BOB_REMOTE_OCR_TLS_CA_PEM=CA,
            BOB_REMOTE_OCR_TOKEN=TOKEN)
        values.update(kwargs)
        return patch.dict(os.environ, values, clear=True)

    def test_default_off_and_cost_lock_both_block_network(self):
        opener = Mock()
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(remote.recognize({"png": IMAGE}, opener=opener))
        for policy in ("", "free_tier", "metered_risk_explicitly_accepted"):
            with self.settings(BOB_REMOTE_OCR_COST_POLICY=policy):
                self.assertIsNone(remote.recognize({"png": IMAGE}, opener=opener))
        opener.open.assert_not_called()

    def test_url_must_match_explicit_global_ip_and_https_port(self):
        invalid = [
            "http://9.9.9.9:8443/ocr",
            "https://9.9.9.9:443/ocr",
            "https://93.184.216.34:8443/ocr",
            "https://10.0.0.4:8443/ocr",
            "https://9.9.9.9:8443/other",
            "https://9.9.9.9:8443/ocr?token=x",
            "https://evil.example:8443/ocr",
        ]
        for url in invalid:
            with self.settings(BOB_REMOTE_OCR_URL=url):
                with self.assertRaises(remote.RemoteOcrError):
                    remote.recognize({"png": IMAGE}, opener=Mock())
        with self.settings(BOB_REMOTE_OCR_ALLOWED_IP="10.0.0.4"):
            with self.assertRaises(remote.RemoteOcrError):
                remote.recognize({"png": IMAGE}, opener=Mock())

    def test_missing_cert_and_wrong_key_block_before_network(self):
        for changes in (dict(BOB_REMOTE_OCR_TLS_CA_PEM=""),
                        dict(BOB_REMOTE_OCR_TOKEN="short")):
            opener = Mock()
            with self.settings(**changes):
                with self.assertRaises(remote.RemoteOcrError):
                    remote.recognize({"png": IMAGE}, opener=opener)
            opener.open.assert_not_called()

    def test_invalid_certificate_cannot_be_silently_trusted(self):
        with self.settings(), self.assertRaises(remote.RemoteOcrError):
            remote.recognize({"png": IMAGE}, opener=Mock())

    def test_valid_certificate_context_and_image_digest(self):
        digest = hashlib.sha256(base64.b64decode(IMAGE)).hexdigest()
        response = json.dumps({"sha256": digest, "passes": ["one", "two"]}).encode()
        opener = Mock()
        opener.open.return_value = FakeResponse(response)
        with self.settings(), patch.object(remote.ssl, "create_default_context", return_value=Mock()) as trust:
            self.assertEqual(remote.recognize({"png": IMAGE}, opener=opener), [["one", "two"]])
        self.assertEqual(trust.call_args.kwargs["cadata"], CA)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("X-bob-ocr-key"), TOKEN)
        self.assertEqual(json.loads(request.data)["sha256"], digest)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 70)

    def test_cross_image_and_incomplete_results_rejected(self):
        digest = hashlib.sha256(base64.b64decode(IMAGE)).hexdigest()
        for result in ({"sha256": "0" * 64, "passes": ["a", "b"]},
                       {"sha256": digest, "passes": ["one"]},
                       {"sha256": digest, "passes": ["one", "two"], "approved": True}):
            opener = Mock()
            opener.open.return_value = FakeResponse(json.dumps(result).encode())
            with self.settings(), patch.object(remote.ssl, "create_default_context", return_value=Mock()), \
                 self.assertRaises(remote.RemoteOcrError):
                remote.recognize({"png": IMAGE}, opener=opener)

    def test_no_redirect_or_retry_after_provider_failure(self):
        with self.assertRaises(remote.RemoteOcrError):
            remote._NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, "https://evil.example/ocr")
        opener = Mock()
        opener.open.side_effect = TimeoutError("provider unavailable")
        with self.settings(), patch.object(remote.ssl, "create_default_context", return_value=Mock()), \
             self.assertRaises(remote.RemoteOcrError):
            remote.recognize({"png": IMAGE}, opener=opener)
        self.assertEqual(opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
