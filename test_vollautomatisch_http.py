"""Integration smoke test: authenticated read-only paper API and panel injection."""
import base64
import json
import os
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

os.environ.setdefault("BOB_USER", "paper-ci-user")
os.environ.setdefault("BOB_PASSWORD", "paper-ci-password")


class PaperHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server_module = server
        cls.original_credentials = (server.USER, server.PASSWORD)
        server.USER, server.PASSWORD = "paper-ci-user", "paper-ci-password"
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.http.server_port}/api/vollautomatisch/demo"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=5)
        cls.server_module.USER, cls.server_module.PASSWORD = cls.original_credentials

    def test_shell_contains_demo_and_script(self):
        html = self.server_module.HTML.decode("utf-8")
        self.assertIn('id="bob-vollautomatisch-demo"', html)
        self.assertIn('id="bobAutoDemoRun"', html)
        self.assertIn('/api/vollautomatisch/demo', html)

    def test_demo_requires_authentication(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url, timeout=5)
        self.assertEqual(error.exception.code, 401)

    def test_authenticated_paper_result(self):
        b64 = base64.b64encode(
            (self.server_module.USER + ":" + self.server_module.PASSWORD).encode()
        ).decode()
        request = Request(self.url, headers={"Authorization": "Basic " + b64})
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            result = json.load(response)
        self.assertEqual(result["mode"], "PAPER_ONLY")
        self.assertFalse(result["live_order_capable"])
        self.assertTrue(result["synthetic"])
        self.assertGreater(result["quotes_processed"], 0)


if __name__ == "__main__":
    unittest.main()
