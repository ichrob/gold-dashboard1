"""Public Android association, no redirects, no secret or order capability."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import bob_app_links


class PublicCertificateTests(unittest.TestCase):
    def test_read_pin_fails_closed_when_missing_or_incorrect(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"cert"
            self.assertIsNone(bob_app_links.read_public_pin(path))
            for bad in ("", "unknown", "a"*63, "g"*64, "a"*65,
                        "AA"*32+"\nPRIVATE_KEY=123", "a"*32 + ":" + "b"*32):
                path.write_text(bad)
                self.assertIsNone(bob_app_links.read_public_pin(path))
            path.write_text("ab"*32 + "\n")
            self.assertEqual(bob_app_links.read_public_pin(path), "AB:"*31+"AB")
    def test_association_exact_package_and_single_pinned_certificate(self):
        pin="AB:"*31+"AB"
        data=bob_app_links.association(pin)
        self.assertEqual(data[0]["target"]["package_name"],
                         "ch.bob.degirocompanion.stable")
        self.assertEqual(data[0]["relation"],
                         ["delegate_permission/common.handle_all_urls"])
        self.assertEqual(data[0]["target"]["sha256_cert_fingerprints"],[pin])
        with self.assertRaises(ValueError):
            bob_app_links.association("A"*64)


class HttpAssetLinksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.httpd=server.ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
    def request(self, method, path):
        conn=http.client.HTTPConnection("127.0.0.1",self.httpd.server_port,timeout=5)
        try:
            conn.request(method,path)
            r=conn.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conn.close()
    def test_unauthenticated_android_validation_no_redirects(self):
        with patch.object(bob_app_links,"read_public_pin",return_value="AB:"*31+"AB"):
            code,headers,body=self.request("GET","/.well-known/assetlinks.json")
            self.assertEqual(code,200)
            self.assertEqual(headers["Content-Type"],"application/json")
            self.assertNotIn("Location",headers)
            self.assertEqual(len(body),int(headers["Content-Length"]))
            parsed=json.loads(body)
            self.assertEqual(parsed,bob_app_links.association("AB:"*31+"AB"))
            code,_,body=self.request("HEAD","/.well-known/assetlinks.json")
            self.assertEqual(code,200)
            self.assertEqual(body,b"")
            code,_,body=self.request("GET","/.well-known/assetlinks.json?secret=x")
            self.assertEqual(code,404)
            self.assertEqual(body,b"")
    def test_no_pin_never_pretends_association_exists(self):
        with patch.object(bob_app_links,"read_public_pin",return_value=None):
            code,headers,body=self.request("GET","/.well-known/assetlinks.json")
        self.assertEqual(code,503)
        self.assertEqual(headers["Cache-Control"],"no-store")
        self.assertEqual(body,b"")


if __name__=="__main__":
    unittest.main()
