import hashlib
import io
import unittest
from unittest.mock import patch
import ocr_assets


class Handler:
    command = "GET"

    def __init__(self):
        self.wfile = io.BytesIO()
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_error(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass


class AssetsTests(unittest.TestCase):
    def setUp(self):
        ocr_assets._cache.clear()

    def test_fixed_paths_only(self):
        with patch("ocr_assets.urlopen") as fetch:
            for path in ("../server.py", "https://example.com", "eng.traineddata.gz/extra"):
                handler = Handler()
                ocr_assets.serve(handler, ocr_assets.PREFIX + path)
                self.assertEqual(handler.status, 404)
            fetch.assert_not_called()

    def test_integrity_cache_and_no_forwarded_headers(self):
        data = b"verified OCR engine"
        with patch.dict(ocr_assets.ASSETS, {"worker.min.js": ["https://cdn.jsdelivr.net/fixed", hashlib.sha256(data).hexdigest()]}):
            with patch("ocr_assets.urlopen", return_value=io.BytesIO(data)) as fetch:
                self.assertEqual(ocr_assets.load("worker.min.js"), data)
                self.assertEqual(ocr_assets.load("worker.min.js"), data)
                fetch.assert_called_once_with("https://cdn.jsdelivr.net/fixed", timeout=20)
        handler = Handler()
        ocr_assets.serve(handler, ocr_assets.PREFIX + "worker.min.js")
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.wfile.getvalue(), data)
        self.assertEqual(handler.headers["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertNotIn("unsafe-eval", handler.headers["Content-Security-Policy"].split())

    def test_invalid_asset_is_not_cached_and_can_retry(self):
        for value in (b"tampered", b"x" * (ocr_assets.MAX_BYTES + 1)):
            handler = Handler()
            with patch("ocr_assets.urlopen", return_value=io.BytesIO(value)):
                ocr_assets.serve(handler, ocr_assets.PREFIX + "tesseract.min.js")
            self.assertEqual(handler.status, 503)
            self.assertEqual(handler.wfile.getvalue(), b"")
            self.assertNotIn("tesseract.min.js", ocr_assets._cache)
            self.assertEqual(handler.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
