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
        with patch.dict(os.environ, {"BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}, clear=True), patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "not-configured")
            post.assert_not_called()

    def test_free_plan_not_confirmed_stops_request(self):
        with patch.dict(os.environ, {"BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BROWSERLESS_API_TOKEN": "private"}, clear=True), patch.object(b.requests, "post") as post:
            self.assertEqual(b.readiness()["state"], "free-plan-unconfirmed")
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "free-plan-unconfirmed")
            self.assertFalse(b.readiness()["canStart"])
            post.assert_not_called()

    def test_readiness_never_exposes_token(self):
        with patch.dict(os.environ, {"BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1",
                                     "BROWSERLESS_API_TOKEN": "private-secret"}, clear=True):
            ready=b.readiness()
            self.assertTrue(ready["canStart"])
            self.assertFalse(ready["providerQuotaVerified"])
            self.assertNotIn("private-secret", json.dumps(ready))

    def test_disabled_does_not_call_cloud(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private"}, clear=True), patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "disabled")
            post.assert_not_called()

    def test_no_arbitrary_url_or_unchecked_isin(self):
        with patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("https://degiro.example.com", now=self.now)["state"], "invalid-isin")
            self.assertEqual(b.extract("DE000FG77FN1", source="degiro", now=self.now)["state"], "unsupported-source")
            post.assert_not_called()

    def test_bnp_static_public_source(self):
        self.assertEqual(b.page_url("DE000BY7UKR4","bnp"),
                         "https://derivate.bnpparibas.com/product-details/DE000BY7UKR4/")
        with patch.object(b.requests, "post") as post:
            self.assertEqual(b.extract("DE000BY7UKR4",source="degiro",now=self.now)["state"],"unsupported-source")
            post.assert_not_called()

    def test_public_fixed_origin_and_unverified_output(self):
        markdown = """# Gold Turbo ISIN DE000FG77FN1
## Stammdaten
Typ
Put
Knock-Out-Barriere
4.151,2285 USD
Basiswert
Gold
"""
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps({
            "ok": True, "statusCode": 200, "strategy": "http-fetch",
            "markdown": markdown, "json": None
        }).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}), patch.object(b.requests,"post") as post:
            post.return_value.__enter__.return_value = response
            result=b.extract("DE000FG77FN1",now=self.now)
            self.assertEqual(result["state"],"unverified-research")
            self.assertEqual(result["fields"]["direction"],"SHORT")
            self.assertEqual(result["fields"]["knockOut"],"4.151,2285 USD")
            self.assertNotIn("bid",result["fields"])
            self.assertFalse(result["aiExtractionUsed"])
            self.assertFalse(result["tradeApproved"])
            self.assertFalse(result["originalQuoteTimeVerified"])
            self.assertEqual(post.call_args.args[0],b.API_EU)
            self.assertEqual(post.call_args.kwargs["json"]["formats"],["markdown","rawText"])
            self.assertNotIn("jsonOptions",post.call_args.kwargs["json"])
            self.assertEqual(post.call_args.kwargs["json"]["proxy"],"datacenter")
            self.assertFalse(post.call_args.kwargs["json"]["onlyMainContent"])
            self.assertEqual(post.call_args.kwargs["json"]["url"],"https://www.sg-zertifikate.de/product-details/fg77fn")
            self.assertEqual(b.extract("DE000FG77FN1",now=self.now)["state"],"already-attempted")
            self.assertEqual(post.call_count,1)

    def test_identity_absent_or_ai_disagrees(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}), patch.object(b.requests, "post") as post:
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

    def test_failed_source_status_and_invalid_bnp_json_isin_are_rejected(self):
        response=MagicMock()
        response.status_code=200
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN":"private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH":"1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED":"1"}),patch.object(b.requests,"post") as post:
            post.return_value.__enter__.return_value=response
            response.iter_content.return_value=[json.dumps({
                "ok":True,"statusCode":403,
                "markdown":"DE000BY7UKR4",
                "json":{"isin":"DE000BY7UKR4"}
            }).encode()]
            self.assertEqual(b.extract("DE000BY7UKR4",source="bnp",now=self.now)["state"],"source-http-unavailable")
            b._RESERVED.clear()
            response.iter_content.return_value=[json.dumps({
                "ok":True,"statusCode":200,"markdown":"DE000BY7UKR4",
                "json":{"isin":None}
            }).encode()]
            self.assertEqual(b.extract("DE000BY7UKR4",source="bnp",now=self.now)["state"],"extraction-not-proven")

    def test_sg_wkn_title_fallback_is_research_only(self):
        markdown = """# BEST Turbo on Gold
## FB0A49
Stammdaten
WKN FB0A49
Produktart BEST Turbo-Optionsscheine
Basiswert Gold
Knock-Out-Barriere 4.151,2285 USD
"""
        self.assertEqual(b.source_identity_evidence(markdown, "DE000FB0A490", "sg"),
                         "sg-product-title-wkn-only")
        self.assertIsNone(b.source_identity_evidence(markdown, "DE000FB0A490", "comdirect"))
        data = {"ok": True, "statusCode": 200, "strategy": "http-fetch",
                "markdown": markdown, "json": {"wkn": "FB0A49", "direction": "Put",
                "knockOut": "4.151,2285 USD", "quoteTime": "unknown"}}
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps(data).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}), \
                patch.object(b.requests, "post") as post:
            post.return_value.__enter__.return_value = response
            result = b.extract("DE000FB0A490", now=self.now)
        self.assertEqual(result["state"], "unverified-research")
        self.assertEqual(result["sourceIdentityEvidence"], "sg-product-title-wkn-only")
        self.assertTrue(result["sourceIdentityLimited"])
        self.assertFalse(result["sourceIsinObserved"])
        self.assertFalse(result["eligible"])
        self.assertFalse(result["tradeApproved"])
        self.assertFalse(result["originalQuoteTimeVerified"])
        post.assert_called_once()

    def test_html_only_identity_is_diagnostic_not_approval(self):
        response=MagicMock()
        response.status_code=200
        body={"ok":True,"statusCode":200,"strategy":"browser",
              "markdown":"# SG website home\nLots of content, no product",
              "rawText":"SG navigation products generic",
              "content":"<html><script>const product='DE000FB0A490';</script></html>",
              "metadata":{"title":"SG Zertifikate - Startseite","sourceURL":"https://www.sg-zertifikate.de/product-details/fb0a49"},
              "attempted":["http-fetch","http-proxy","browser"],
              "json":None}
        response.iter_content.return_value=[json.dumps(body).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN":"secret",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH":"1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED":"1"}),patch.object(b.requests,"post") as post:
            post.return_value.__enter__.return_value=response
            result=b.extract("DE000FB0A490",now=self.now)
        self.assertEqual(result["state"],"identity-not-proven")
        self.assertTrue(result["diagnostics"]["hasExactIsinInRawHtmlOnly"])
        self.assertFalse(result["diagnostics"]["hasExactIsinInRawTextOnly"])
        self.assertEqual(result["diagnostics"]["browserlessRegion"],"ams")
        self.assertEqual(result["diagnostics"]["strategyAttempted"],["http-fetch","http-proxy","browser"])
        self.assertEqual(result["diagnostics"]["sourceTitleClass"],"issuer-generic")
        self.assertFalse(result["tradeApproved"])
        self.assertFalse(result["fields"])
        self.assertNotIn("DE000FB0A490';</script>",json.dumps(result))
        self.assertNotIn("secret",json.dumps(result))

    def test_sg_wkn_lookalikes_are_not_identity(self):
        isin = "DE000FB0A490"
        valid = "## FB0A49\nStammdaten\nBasiswert Gold\nKnock-Out-Barriere 4151 USD"
        cases = [
            "# Produkte\nFB0A49\nStammdaten\nBasiswert Gold\nKnock-Out-Barriere 4151",
            "## FB0A49\nStammdaten\nBasiswert Gold",
            "## FB0A40\nStammdaten\nBasiswert Gold\nKnock-Out-Barriere 4151",
            valid + "\nISIN DE000FG77FN1",
            "# Artikel\nDas Symbol FB0A49 ist hier erwähnt\nStammdaten\nBasiswert Gold\nKnock-Out-Barriere 4151",
        ]
        for page in cases:
            with self.subTest(page=page[:45]):
                self.assertIsNone(b.source_identity_evidence(page, isin, "sg"))
        self.assertEqual(b.source_identity_evidence(
            "Stammdaten ISIN DE000FB0A490", isin, "sg"), "exact-isin-in-page")
        self.assertIsNone(b.source_identity_evidence(
            "Stammdaten ISIN DE000FG77FN1", isin, "sg"))

    def test_wkn_page_with_another_full_isin_still_rejected(self):
        response=MagicMock()
        response.status_code=200
        response.iter_content.return_value=[json.dumps({
            "ok":True,"statusCode":200,
            "markdown":"## FB0A49\nStammdaten\nBasiswert\nGold\nKnock-Out-Barriere\n4.151,2285 USD\nISIN DE000FG77FN1",
            "json":{"isin":"DE000FB0A490","wkn":"FB0A49"}
        }).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN":"private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH":"1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED":"1"}),patch.object(b.requests,"post") as post:
            post.return_value.__enter__.return_value=response
            result=b.extract("DE000FB0A490",now=self.now)
        self.assertEqual(result["state"],"identity-not-proven")
        self.assertFalse(result["eligible"])
        self.assertEqual(result["fields"],{})

    def test_identity_failure_diagnostics_are_anonymous(self):
        secret = "PRIVATE_API_KEY_DO_NOT_EXPOSE"
        page = "## SG Shop\nCookie banner - another page; no matching product"
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps({
            "ok": True, "statusCode": 200,
            "strategy": "http-fetch", "markdown": page,
            "json": {"isin": "DE000FB0A490"}
        }).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": secret,
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}), \
                patch.object(b.requests, "post") as post:
            post.return_value.__enter__.return_value = response
            result = b.extract("DE000FB0A490", now=self.now)
        self.assertEqual(result["state"], "identity-not-proven")
        self.assertEqual(result["diagnostics"]["providerStrategy"], "http-fetch")
        self.assertFalse(result["diagnostics"]["hasExactIsin"])
        self.assertFalse(result["diagnostics"]["hasMatchingWknHeading"])
        self.assertFalse(result["diagnostics"]["hasProductMarkers"])
        self.assertTrue(result["diagnostics"]["sgFullContentRequested"])
        self.assertFalse(result["tradeApproved"])
        self.assertFalse(result["eligible"])
        self.assertFalse(result["fields"])
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(page, json.dumps(result))

    def test_identity_diagnostic_classifies_challenge_without_leaking_text(self):
        page = "Just a moment... Cloudflare Challenge\nnot the requested product"
        d = b.safe_page_diagnostics(page, "DE000FB0A490", "sg", "browser")
        self.assertTrue(d["possibleChallenge"])
        self.assertEqual(d["markdownSizeClass"], "short")
        self.assertNotIn(page, json.dumps(d))
        self.assertFalse(d["hasExactIsin"])
        self.assertFalse(d["hasMatchingWknHeading"])

    def test_main_content_other_sources_remains_stripped(self):
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [json.dumps({
            "ok": True, "statusCode": 200, "strategy": "http-fetch",
            "markdown": "ISIN DE000BY7UKR4",
            "json": {"isin": "DE000BY7UKR4"}
        }).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "PRIVATE",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}), \
                patch.object(b.requests, "post") as post:
            post.return_value.__enter__.return_value = response
            result = b.extract("DE000BY7UKR4", source="bnp", now=self.now)
        self.assertEqual(result["state"], "unverified-research")
        self.assertTrue(post.call_args.kwargs["json"]["onlyMainContent"])

    def test_sg_ai_json_does_not_change_markdown_only_evidence(self):
        response=MagicMock()
        response.status_code=200
        page="## FB0A49\n## Stammdaten\nTyp\nPut\nBasiswert\nGold\nKnock-Out-Barriere\n4.151,2285 USD"
        response.iter_content.return_value=[json.dumps({
            "ok":True,"statusCode":200,"markdown":page,
            "json":{"isin":"DE000FG77FN1","wkn":"DIFFERENT","quoteTime":"fake","bid":"99999"}
        }).encode()]
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN":"private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH":"1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED":"1"}),patch.object(b.requests,"post") as post:
            post.return_value.__enter__.return_value=response
            result=b.extract("DE000FB0A490",now=self.now)
        self.assertEqual(result["state"],"unverified-research")
        self.assertEqual(result["fields"]["direction"],"SHORT")
        self.assertEqual(result["sourceIdentityEvidence"],"sg-product-title-wkn-only")
        self.assertNotIn("bid",result["fields"])
        self.assertNotIn("quoteTime",result["fields"])
        self.assertFalse(result["aiExtractionUsed"])
        self.assertFalse(result["eligible"])

    def test_exception_is_redacted(self):
        with patch.dict(os.environ, {"BROWSERLESS_API_TOKEN": "private",
                                     "BOB_BROWSERLESS_PUBLIC_RESEARCH": "1",
                                     "BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED": "1"}), patch.object(b.requests, "post", side_effect=ValueError("private")):
            self.assertEqual(b.extract("DE000FG77FN1", now=self.now)["state"], "request-failed")
            self.assertNotIn("private", json.dumps(b.extract("DE000FG77FN1", now=self.now)))

if __name__ == "__main__":
    unittest.main()
