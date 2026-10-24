import http.client
import threading
import unittest
from unittest.mock import patch

import bob_handy_landing


class PureLandingTests(unittest.TestCase):
    def test_exact_known_page(self):
        for command in bob_handy_landing.PAGES:
            self.assertEqual(command, bob_handy_landing.route("/handy/" + command))
            body = bob_handy_landing.render_page(command).decode()
            self.assertIn('href="bobhandy://handoff/' + command + '"', body)
            self.assertNotIn("DEGIRO_LOGIN", body)
            self.assertNotIn("PLACE_ORDER", body)
            self.assertIn("Bob – Handy öffnen", body)

    def test_allow_only_exact_chatgpt_attribution(self):
        for command in bob_handy_landing.PAGES:
            self.assertEqual(
                bob_handy_landing.route("/handy/" + command,
                                        "utm_source=chatgpt.com"), command)
        for query in ("utm_source=other", "utm_source=chatgpt.com&action=buy",
                      "utm_source=chatgpt.com&utm_source=chatgpt.com",
                      "utm_source=chatgpt%2Ecom", "utm_source=chatgpt.com&"):
            self.assertIsNone(bob_handy_landing.route(
                "/handy/OPEN_PRODUCTS", query))
        self.assertIsNone(bob_handy_landing.route(
            "/handy/PLACE_ORDER", "utm_source=chatgpt.com"))

    def test_reject_all_unknown_query_or_attempted_injection(self):
        for path, query in (
            ("/handy/PLACE_ORDER", ""),
            ("/handy/OPEN_SETTINGS", ""),
            ("/handy/OPEN_PRODUCTS/", ""),
            ("/handy/OPEN_PRODUCTS%0A", ""),
            ("/handy/../../api/live", ""),
            ("/handy/OPEN_PRODUCTS", "to=https://malicious.example"),
            ("/handy/OPEN_PRODUCTS", "x=1"),
            ("/handy/OPEN_PRODUCTS\\n", ""),
            ("/handy/OPEN_PRODUCTS;BUY", ""),
            ("/HANDY/OPEN_PRODUCTS", ""),
        ):
            self.assertIsNone(bob_handy_landing.route(path, query))


class HttpLandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.server_module = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, authenticated):
        with patch.object(self.server_module.Handler, "authenticated", return_value=authenticated):
            conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
            try:
                conn.request(method, path)
                resp = conn.getresponse()
                return resp.status, dict(resp.getheaders()), resp.read()
            finally:
                conn.close()

    def test_private_no_content_without_authentication(self):
        status, headers, body = self.request("GET", "/handy/OPEN_PRODUCTS", False)
        self.assertEqual(303, status)
        self.assertEqual("/login?view=products", headers["Location"])
        self.assertNotIn(b"bobhandy://", body)

    def test_authenticated_page_only_offers_an_app_link(self):
        status, headers, body = self.request("GET", "/handy/OPEN_PRODUCTS", True)
        self.assertEqual(200, status)
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertEqual("no-referrer", headers["Referrer-Policy"])
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn(b'bobhandy://handoff/OPEN_PRODUCTS', body)
        self.assertIn(b'/?view=products#products', body)
        self.assertNotIn(b"<script", body.lower())
        self.assertNotIn(b"window.location", body)
        self.assertNotIn(b"access_token", body)

    def test_attributed_link_keeps_authentication_and_unknowns_rejected(self):
        allowed = "/handy/OPEN_PRODUCTS?utm_source=chatgpt.com"
        status, headers, _ = self.request("GET", allowed, False)
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/login?view=products")
        status, headers, body = self.request("GET", allowed, True)
        self.assertEqual(status, 200)
        self.assertIn(b"bobhandy://handoff/OPEN_PRODUCTS", body)
        self.assertNotIn(b"utm_source=chatgpt.com", body)
        status, _, body = self.request("HEAD", allowed, True)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        for invalid in (allowed + "&buy=1", allowed + "&utm_source=chatgpt.com"):
            status, _, body = self.request("GET", invalid, True)
            self.assertEqual(status, 404)
            self.assertNotIn(b"bobhandy://", body)

    def test_head_respects_auth_and_is_bodyless(self):
        status, headers, body = self.request("HEAD", "/handy/OPEN_PRODUCTS", True)
        self.assertEqual(200, status)
        self.assertGreater(int(headers["Content-Length"]), 150)
        self.assertEqual(b"", body)
        status, headers, body = self.request("HEAD", "/handy/OPEN_PRODUCTS", False)
        self.assertEqual(303, status)
        self.assertEqual(b"", body)

    def test_forbidden_routes_fail_closed_without_data_leak(self):
        for path in ["/handy/PLACE_ORDER", "/handy/OPEN_PRODUCTS?buy=1"]:
            for method in ["GET", "HEAD"]:
                status, _, body = self.request(method, path, True)
                self.assertEqual(404, status)
                self.assertNotIn(b"bobhandy://", body)


if __name__ == "__main__":
    unittest.main()
