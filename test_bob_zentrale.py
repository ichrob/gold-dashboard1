"""Non-destructive PWA, auth, scope and no-cache regression tests."""
import io
import json
import unittest
from unittest.mock import patch
import bob_zentrale

class FakeHandler:
    def __init__(self, path):
        self.path=path
        self.headers={}
        self.wfile=io.BytesIO()
        self.status=None
        self.response_headers={}
    def send_response(self, value): self.status=value
    def send_header(self, key, value): self.response_headers[key]=value
    def end_headers(self): pass

class ZentraleTests(unittest.TestCase):
    def test_index_requires_existing_bob_auth(self):
        h=FakeHandler("/zentrale/")
        with patch("bob_auth.authenticated", return_value=False):
            self.assertTrue(bob_zentrale.route(h,"demo","pw"))
        self.assertEqual(h.status,303)
        self.assertEqual(h.response_headers.get("Location"),"/login")
        self.assertEqual(h.wfile.getvalue(),b"")

    def test_private_shell_get_head_and_response_policy(self):
        with patch("bob_auth.authenticated", return_value=True):
            h=FakeHandler("/zentrale/")
            self.assertTrue(bob_zentrale.route(h,"demo","pw"))
            head=FakeHandler("/zentrale/")
            self.assertTrue(bob_zentrale.route(head,"demo","pw",head=True))
        self.assertEqual(h.status,200)
        self.assertIn(b"Bob Zentrale",h.wfile.getvalue())
        self.assertEqual(head.wfile.getvalue(),b"")
        self.assertEqual(int(head.response_headers["Content-Length"]),len(h.wfile.getvalue()))
        self.assertEqual(h.response_headers["Cache-Control"],"no-store")
        self.assertIn("default-src 'none'",h.response_headers["Content-Security-Policy"])

    def test_install_identity_and_network_only_private_scope(self):
        manifest=FakeHandler("/zentrale/manifest.webmanifest")
        self.assertTrue(bob_zentrale.route(manifest,"unused","unused"))
        obj=json.loads(manifest.wfile.getvalue())
        self.assertEqual((obj["id"],obj["scope"],obj["start_url"]),("/zentrale/","/zentrale/","/zentrale/"))
        sw=FakeHandler("/zentrale/sw.js")
        self.assertTrue(bob_zentrale.route(sw,"unused","unused"))
        self.assertNotIn(b"caches.open",sw.wfile.getvalue())
        self.assertNotIn(b"cache.put",sw.wfile.getvalue())
        app=FakeHandler("/zentrale/app.js")
        self.assertTrue(bob_zentrale.route(app,"unused","unused"))
        self.assertIn(b"/api/operations-summary",app.wfile.getvalue())
        self.assertNotIn(b"method:\"POST\"",app.wfile.getvalue())
        self.assertNotIn(b"innerHTML",app.wfile.getvalue())

    def test_unknown_and_query_do_not_leak_private_content(self):
        self.assertFalse(bob_zentrale.route(FakeHandler("/zentrale/delete"),"u","p"))
        h=FakeHandler("/zentrale/?x=1")
        self.assertTrue(bob_zentrale.route(h,"u","p"))
        self.assertEqual(h.status,404)
        self.assertEqual(h.wfile.getvalue(),b"")

if __name__=="__main__": unittest.main()
