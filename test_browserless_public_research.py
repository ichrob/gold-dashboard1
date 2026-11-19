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
        body = {"ok": True, "statusCode": 200, "strategy": "http-fetch", "markdown": "Produkt ISIN DE000FG77FN1 Gold Turbo",
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
            self.assertEqual(result["providerStrategy"], "http-fetch")
            self.assertEqual(post.call_args.kwargs["json"]["proxy"], "datacenter")
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
                {"ok": True, "statusCode": 200, "strategy": "http-fetch", "markdown": "Another product", "json": {"isin": "DE000FG77FN1"}}
            ).encode()]
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "identity-not-proven")

    def test_limited_to_three_calls_per_day(self):
        for i in range(3):
            self.assertEqual(b._reserve("ISIN" + str(i), "sg", self.now), "reserved")
        self.assertEqual(b._reserve("ISIN3", "sg", self.now), "day-limit")
        self.assertEqual(b._reserve("ISIN0", "sg", self.now), "already-attempted")

    def test_twelve_attempts_in_month_even_across_days(self):
        from datetime import timedelta
        for i in range(12):
            day = self.now + timedelta(days=i // 3)
            self.assertEqual(b._reserve("ISIN" + str(i), "sg", day), "reserved")
        self.assertEqual(b._reserve("ISIN12", "sg", self.now + timedelta(days=5)), "month-limit")
        self.assertEqual(b._reserve("ISIN12", "sg", datetime(2026, 12, 1, tzinfo=timezone.utc)), "reserved")

    def test_failed_source_status_and_invalid_json_isin_are_rejected(self):
        response = MagicMock()
        response.status_code = 200
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1"}), patch.object(b.requests, "post") as post:
            post.return_value.__enter__.return_value = response
            response.iter_content.return_value = [json.dumps(
                {"ok": True, "statusCode": 403, "markdown": "DE000FG77FN1",
                 "json": {"isin": "DE000FG77FN1"}}
            ).encode()]
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "source-http-unavailable")
            b._RESERVED.clear()
            response.iter_content.return_value = [json.dumps(
                {"ok": True, "statusCode": 200, "markdown": "DE000FG77FN1",
                 "json": {"isin": None}}
            ).encode()]
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "extraction-not-proven")

    def test_exception_is_redacted(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1"}), patch.object(b.requests, "post", side_effect=ValueError("private")):
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "request-failed")
            self.assertNotIn("private", json.dumps(b.extract("DE000FG77FN1", now=self.now)))

if __name__ == "__main__":
    unittest.main()
