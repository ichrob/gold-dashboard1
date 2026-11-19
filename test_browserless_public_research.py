import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import browserless_public_research as b


class PublicBrowserlessTests(unittest.TestCase):
    def setUp(self):
        b._RESERVED.clear()
        self.now = datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)

    def test_no_secret_does_not_call_cloud(self):
        with patch.dict(os.environ, {"BOB_BROWSERLESS_PUBLIC_RESEARCH": "1"}, clear=True), patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "not-configured")
            post.assert_not_called()

    def test_disabled_does_not_call_cloud(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private"}, clear=True), patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "disabled")
            post.assert_not_called()

    def test_no_arbitrary_url_or_unchecked_isin(self):
        with patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("https://degiro.example.com", now=self.now)["state"], "invalid-isin")
            self.assertEqual(b.extract("DE000FG77FN1", source="degiro", now=self.now)["state"], "unsupported-source")
            post.assert_not_called()

    def test_public_fixed_origin_and_unverified_output(self):
        body = {"ok": True, "markdown": "Produkt ISIN DE000FG77FN1 Gold Turbo",
                "json": {"isin": "DE000FG77FN1", "bid": "0,63 EUR",
                         "quoteTime": "19.11.2026 20:15", "leverage": "8,2"}}
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps(body).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1"}), patch.object(b.requests, "post") as post:
            post.return_value.__enter__.return_value = response
            result = b.extract("DE000FG77FN1", now=self.now)
            self.assertEqual(result["state"], "unverified-research")
            self.assertFalse(result["eligible"])
            self.assertFalse(result["tradeApproved"])
            self.assertFalse(result["originalQuoteTimeVerified"])
            self.assertEqual(result["fields"]["bid"], "0,63 EUR")
            self.assertEqual(post.call_args.args[0], b.API)
            self.assertEqual(post.call_args.kwargs["json"]["url"],
                             "https://www.sg-zertifikate.de/product-details/fg77fn")
            self.assertNotIn("cookie", str(post.call_args.kwargs).lower())
            self.assertFalse(post.call_args.kwargs["allow_redirects"])
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "already-attempted")
            self.assertEqual(post.call_count, 1)

    def test_identity_absent_or_ai_disagrees(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1"}), patch.object(b.requests, "post") as post:
            response = post.return_value.__enter__.return_value
            response.status_code = 200
            response.iter_content.return_value = [json.dumps(
                {"ok": True, "markdown": "Another product", "json": {"isin": "DE000FG77FN1"}}
            ).encode()]
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "identity-not-proven")

    def test_exception_is_redacted(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1"}), patch.object(b.requests, "post", side_effect=ValueError("private")):
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "request-failed")
            self.assertNotIn("private", json.dumps(b.extract("DE000FG77FN1", now=self.now)))

if __name__ == "__main__":
    unittest.main()
