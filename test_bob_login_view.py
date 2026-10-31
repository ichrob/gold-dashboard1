"""Regression: Android Bob sections survive explicit password login, safely."""
import io
import unittest
from unittest.mock import patch

import bob_auth


class FakeHandler:
    command = "GET"

    def __init__(self):
        self.status = None
        self.headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers.append((name, value))

    def end_headers(self):
        pass


class LoginViewTests(unittest.TestCase):
    def test_only_exact_ui_views_are_accepted(self):
        for view in ("overview", "products", "products-long", "products-leverage", "trade", "simulation",
                     "learning", "research", "problems"):
            self.assertEqual(bob_auth.safe_return_view(view), view)
            self.assertEqual(bob_auth.login_destination({}, view),
                             "/?view=" + view + "#" + view)
        self.assertEqual(bob_auth.safe_return_view("zentrale"),"zentrale")
        self.assertEqual(bob_auth.login_redirect("view=zentrale"),"/login?view=zentrale")
        self.assertEqual(bob_auth.login_destination({}, "zentrale"),"/zentrale/")
        for value in ("", "https://example.com", "//other.example",
                      "products&redirect=evil", "products#wrong",
                      "products-long/orders", "products-long?buy=true",
                      "../login", "products/order", "products?buy=true",
                      "settings", "degiro", "PRODUCTS", "<script>alert(1)</script>", None):
            self.assertEqual(bob_auth.safe_return_view(value), "")
            self.assertEqual(bob_auth.login_destination({}, value), "/")

    def test_oauth_flow_cannot_be_overridden_by_ui_view(self):
        with patch("bob_oauth.resume_location", return_value="/oauth/resume"):
            self.assertEqual(bob_auth.login_destination({}, "products"),
                             "/oauth/resume")

    def test_login_page_keeps_only_safe_hidden_view(self):
        h = FakeHandler()
        bob_auth.login_page(h, view="products")
        self.assertEqual(h.status, 200)
        page = h.wfile.getvalue().decode("utf8")
        self.assertIn('name="return_view" value="products"', page)
        self.assertIn('name="csrf"', page)
        self.assertIn('name="password" type="password"', page)
        other = FakeHandler()
        bob_auth.login_page(other, view='"><script>alert(1)</script>')
        page = other.wfile.getvalue().decode("utf8")
        self.assertIn('name="return_view" value=""', page)
        self.assertNotIn("<script>alert(1)</script>", page)

    def test_handset_images_survive_login_and_invalid_ids_are_rejected(self):
        batch = "0123456789abcdef" * 2
        self.assertEqual(bob_auth.login_redirect("handset-list=" + batch),
                         "/login?view=products&handset-list=" + batch)
        self.assertEqual(bob_auth.login_destination({}, "products", batch),
                         "/?view=products&handset-list=" + batch + "#bob-morning-images=" + batch)
        handler = FakeHandler()
        bob_auth.login_page(handler, handset_batch=batch)
        self.assertIn('name="handset_batch" value="' + batch + '"', handler.wfile.getvalue().decode())
        with patch("bob_oauth.resume_location", return_value="/oauth/resume"):
            self.assertEqual(bob_auth.login_destination({}, "products", batch), "/oauth/resume")
        for invalid in ("../", "https://example.com", "a"*31, "a"*33, "A"*32, '<script>', None):
            self.assertEqual(bob_auth.safe_handset_batch(invalid), "")
            self.assertEqual(bob_auth.login_destination({}, "products", invalid), "/?view=products#products")
        self.assertEqual(bob_auth.login_redirect("handset-list=bad&view=products"), "/login?view=products")


if __name__ == "__main__":
    unittest.main()
