import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch

import server


class BrowserlessPublicRouteTests(unittest.TestCase):
    def request_once(self, payload, *, authenticated=True, same_origin=True):
        with server.BobHTTPServer(("127.0.0.1", 0), server.Handler) as httpd, \
                patch.object(server.Handler, "authenticated", return_value=authenticated), \
                patch.object(server.bob_auth, "same_origin", return_value=same_origin):
            worker = threading.Thread(target=httpd.handle_request)
            worker.start()
            conn = http.client.HTTPConnection(*httpd.server_address, timeout=3)
            try:
                conn.request("POST", "/api/browserless/public-research",
                             body=json.dumps(payload), headers={"Content-Type": "application/json"})
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()
                worker.join(3)

    def test_status_requires_bob_auth_and_never_exposes_secret(self):
        with server.BobHTTPServer(("127.0.0.1", 0), server.Handler) as httpd, \
                patch.object(server.Handler, "authenticated", return_value=True), \
                patch.dict(os.environ, {"BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                      "BROWSERLESS_API_TOKEN": "private-secret"}, clear=True):
            thread=threading.Thread(target=httpd.handle_request)
            thread.start()
            conn=http.client.HTTPConnection(*httpd.server_address,timeout=3)
            try:
                conn.request("GET","/api/browserless/public-status")
                response=conn.getresponse()
                body=response.read()
            finally:
                conn.close()
                thread.join(3)
        self.assertEqual(response.status,200)
        self.assertNotIn(b"private-secret",body)
        self.assertEqual(json.loads(body)["state"],"free-plan-unconfirmed")

    def test_fails_closed_when_disabled(self):
        with patch.dict(os.environ, {"BOB_BROWSERLESS_PUBLIC_RESEARCH": "0"}, clear=True), \
                patch("browserless_public_research.requests.post") as post:
            status, body = self.request_once({"isin": "DE000FG77FN1", "source": "sg"})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["state"], "disabled")
            post.assert_not_called()

    def test_no_depository_or_untrusted_web_url(self):
        with patch("browserless_public_research.requests.post") as post:
            for source in ["degiro", "https://example.com", "broker-profile"]:
                status, body = self.request_once({"isin": "DE000FG77FN1", "source": source})
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["state"], "invalid-request")
            post.assert_not_called()

    def test_owner_auth_and_same_origin_required(self):
        payload = {"isin": "DE000FG77FN1", "source": "sg"}
        status, _ = self.request_once(payload, authenticated=False)
        self.assertEqual(status, 401)
        status, _ = self.request_once(payload, same_origin=False)
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
