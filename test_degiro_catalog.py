"""Unattended issuer catalogue safety: never claim verified DEGIRO availability."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import degiro_catalog as catalog

Z = ZoneInfo("Europe/Zurich")


def issuer(isin, side="LONG", *, spot=True, status=1, verified=True):
    return dict(isin=isin, productVerified=verified, found=True,
        fresh=True, eligible=True, quoteAt="2026-10-12T08:00:00+02:00",
        sourceUrl="https://www.sg-zertifikate.de/product-details/"+isin.lower(),
        metadata=dict(underlying="XAU/USD", underlyingType="SPOT" if spot else "FUTURE",
                      direction=side, currency="EUR", status=status))


class IssuerCatalogueTests(unittest.TestCase):
    def test_no_deferred_degirosession_or_account_connection(self):
        self.assertGreaterEqual(len(catalog.SEEDS),5)
        self.assertLessEqual(len(catalog.SEEDS),catalog.LIMIT)
        self.assertNotIn("DE000FE4UF01",[a for a,_ in catalog.SEEDS])
        self.assertNotIn("DE000FG5NMF2",[a for a,_ in catalog.SEEDS])
        data=catalog.build(lambda isin:issuer(isin, next(d for i,d in catalog.SEEDS if i==isin)),
                           datetime(2026,10,12,9,tzinfo=Z))
        self.assertFalse(data["completeDegiroCatalog"])
        self.assertFalse(data["canAutoImportVerifiedDegiroList"])
        self.assertFalse(data["degiroAccountConnected"])
        self.assertFalse(data["automaticOrders"])
        self.assertTrue(data["attempted"]<=12)
        for x in data["candidates"]:
            self.assertIsNone(x["degiroListed"])
            self.assertIsNone(x["degiroTradingEnabled"])
            self.assertFalse(x["eligibleForTop3"])
            self.assertFalse(x["liveApproved"])
            self.assertFalse(x["screenshotToday"])

    def test_future_invalid_status_and_mismatch_excluded(self):
        isin="DE000FG309G0"
        item, bad=catalog.normalize(isin,"SHORT",issuer(isin,"SHORT",spot=False))
        self.assertIsNone(item);self.assertIn("Gold-Spot",bad["reason"])
        item, bad=catalog.normalize(isin,"SHORT",issuer(isin,"SHORT",status=2))
        self.assertIsNone(item);self.assertIn("beendet",bad["reason"])
        item, bad=catalog.normalize(isin,"SHORT",issuer(isin,"LONG"))
        self.assertIsNone(item);self.assertIn("weicht",bad["reason"])
        item, bad=catalog.normalize(isin,"SHORT",{**issuer(isin,"SHORT"),"isin":"DE000FG4JXV7"})
        self.assertIsNone(bad);self.assertFalse(item["issuerVerified"])
        self.assertFalse(item["issuerQuoteFresh"])

    def test_no_source_time_fabrication_on_missing_data(self):
        item, bad=catalog.normalize("DE000FC1CHB7","LONG",{})
        self.assertIsNone(bad)
        self.assertIsNone(item["quoteSourceAt"])
        self.assertFalse(item["issuerVerified"])
        self.assertFalse(item["issuerQuoteFresh"])

    def test_no_network_credential_or_delayed_adapter_fallback(self):
        attempts=[]
        def lookup(isin):
            attempts.append(isin)
            raise OSError("upstream unavailable")
        result=catalog.build(lookup,datetime(2026,10,12,9,tzinfo=Z))
        self.assertEqual(result["errors"],len(catalog.SEEDS))
        self.assertEqual(result["status"],"partial")
        self.assertEqual(len(attempts),len(catalog.SEEDS))
        self.assertFalse(any(c["issuerVerified"] for c in result["candidates"]))
        self.assertFalse(any(c["issuerQuoteFresh"] for c in result["candidates"]))

    def test_session_gates_weekends_nights_and_two_daily_scans(self):
        self.assertIsNone(catalog.session(datetime(2026,10,11,10,tzinfo=Z)))
        self.assertIsNone(catalog.session(datetime(2026,10,12,7,tzinfo=Z)))
        self.assertIsNone(catalog.session(datetime(2026,10,12,21,tzinfo=Z)))
        self.assertEqual(catalog.session(datetime(2026,10,12,8,tzinfo=Z))[1],"morning")
        self.assertEqual(catalog.session(datetime(2026,10,12,18,tzinfo=Z))[1],"evening")

    def test_server_endpoint_requires_auth_and_ui_keeps_separate_list(self):
        from pathlib import Path
        py=Path("server.py").read_text()
        js=Path("degiro_assistant.js").read_text()
        self.assertIn('or path == "/api/degiro/candidates"',py)
        self.assertIn('if path == "/api/degiro/candidates":',py)
        self.assertIn('degiro_catalog.start()',py)
        self.assertIn("Automatische Gold-Produktrecherche · externe Kandidaten",js)
        self.assertIn('completeDegiroCatalog!==false',js)
        self.assertIn('p.eligibleForTop3!==false',js)
        self.assertIn("Keine automatische Top-3-Freigabe",js)
        self.assertNotIn('document.querySelector("#dgListUpload").files',js)


if __name__=="__main__":
    unittest.main()
