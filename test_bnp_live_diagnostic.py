"""Temporary, read-only public BNP-source diagnostic for three historical Gold ISINs.

Run only on the isolated ci/bnp-audit branch. It does not touch DEGIRO,
login, private lists, credentials, trading interfaces or order endpoints.
It reports source and validation status only, never trades or private account data.
"""
import unittest

from product_quotes import get_bnp_quote

BNP_HISTORICAL = ("DE000PJ9NCK0", "DE000PJ9NB98", "DE000PG0XK25")


class BnpLiveSourceDiagnostic(unittest.TestCase):
    def test_public_bnp_source_clocks_and_terms(self):
        for index, isin in enumerate(BNP_HISTORICAL, 1):
            with self.subTest(candidate=index):
                q = get_bnp_quote(isin)
                # Print results without quote values or confidential account/list data.
                fields = {
                    "candidate": index,
                    "verified": bool(q.get("productVerified")),
                    "found": bool(q.get("found")),
                    "fresh": bool(q.get("fresh")),
                    "eligible_issuer_only": bool(q.get("eligible")),
                    "marketOpen": q.get("marketOpen"),
                    "bidAt": q.get("bidAt"),
                    "askAt": q.get("askAt"),
                    "leverageAt": q.get("leverageAt"),
                    "snapshotAt": q.get("snapshotAt"),
                    "termsDate": (q.get("metadata") or {}).get("termsDate"),
                    "termsDated": (q.get("metadata") or {}).get("termsDated"),
                    "quoteFailureCode": q.get("quoteFailureCode"),
                    "termsFailureCode": q.get("termsFailureCode"),
                }
                print("BNP_AUDIT " + repr(fields), flush=True)
                # Safety assertion: missing originals NEVER license a fresh quote.
                if not all(q.get(field) for field in ("bidAt", "askAt", "leverageAt", "snapshotAt")):
                    self.assertFalse(q.get("eligible"), "Missing source clock must fail closed")
                self.assertFalse(q.get("isDegiroQuote"), "Research must not claim a DEGIRO executable quote")


if __name__ == "__main__":
    unittest.main()
