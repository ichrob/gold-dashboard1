"""Regression checks for strict private active-list product monitoring."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import degiro_product_audit as audit

NOW = datetime(2026, 10, 13, 9, 5, tzinfo=ZoneInfo("Europe/Zurich")).timestamp()*1000
ISIN = "DE000FG4JXV7"
GEN = "2026-10-13T07:00:00+00:00"


def iso(ms):
    return datetime.fromtimestamp(ms/1000,ZoneInfo("Europe/Zurich")).isoformat()


def provider(now=NOW):
    return {
        "isin": ISIN, "productVerified": True, "found": True,
        "marketOpen": True, "bid": 6.0, "ask": 6.02,
        "bidAt": iso(now-5000), "askAt": iso(now-4500),
        "leverage": 18.4, "leverageAt": iso(now-3000),
        "checkedAt": iso(now), "currency": "EUR", "source": "SG",
        "metadata": {"underlying": "XAU/USD", "underlyingType": "SPOT",
            "status": 1, "direction": "SHORT", "currency": "EUR",
            "ko": 4200., "strike": 4250., "ratio": .1,
            "maturity": "2026-12-18", "termsFixed": True},
    }


def feed():
    return {"listOrigin": "degiro-screenshot", "listUploadedAt": GEN,
            "products": [{"isin":ISIN, "productDirection":"SHORT", "isinConfirmed":True}]}


class ProductAuditTests(unittest.TestCase):
    def test_complete_issuer_evidence_is_never_degiro_trade_approval(self):
        item=audit.examine(feed()["products"][0],provider(),NOW)
        self.assertEqual(item["missing"],[])
        self.assertEqual(item["state"],"issuer-evidence-complete")
        self.assertFalse(item["degiroVerified"])
        self.assertFalse(item["tradeApproved"])

    def test_missing_independent_leverage_clock_fails_closed(self):
        q=provider()
        q.pop("leverageAt")
        q["leverageCalculation"]={"available":True,"fresh":True,"value":18.4}
        item=audit.examine(feed()["products"][0],q,NOW)
        self.assertIn("leverage-time",item["missing"])
        self.assertIsNone(item["leverageSourceAt"])
        self.assertFalse(item["tradeApproved"])

    def test_chart_and_cached_prices_cannot_be_promoted(self):
        q=provider()
        q.update(found=False,priceKind="issuer-chart",isExecutableQuote=False)
        item=audit.examine(feed()["products"][0],q,NOW)
        self.assertIn("quote",item["missing"])
        q=provider()
        q["bidAt"]=iso(NOW-100000)
        item=audit.examine(feed()["products"][0],q,NOW)
        self.assertIn("quote-time",item["missing"])

    def test_ko_requires_specific_evidence_not_just_recent_receipt(self):
        q=provider()
        q["metadata"].pop("termsFixed")
        self.assertIn("ko-time",audit.examine(feed()["products"][0],q,NOW)["missing"])
        q["metadata"].update(termsDated=True,termsDate="2026-10-12")
        self.assertIn("ko-time",audit.examine(feed()["products"][0],q,NOW)["missing"])
        q["metadata"]["termsDate"]="2026-10-13"
        self.assertNotIn("ko-time",audit.examine(feed()["products"][0],q,NOW)["missing"])
        q["checkedAt"]=iso(NOW-9*3600000)
        self.assertIn("ko-time",audit.examine(feed()["products"][0],q,NOW)["missing"])

    def test_factor_future_wrong_direction_and_invalid_identity_block(self):
        for field,value,code in (("type","FACTOR","factor"),
                                 ("underlyingType","FUTURE","future"),
                                 ("direction","LONG","direction")):
            q=provider()
            q["metadata"][field]=value
            self.assertIn(code,audit.examine(feed()["products"][0],q,NOW)["missing"])
        q=provider()
        q["isin"]="DE000FC1CHB7"
        self.assertIn("identity",audit.examine(feed()["products"][0],q,NOW)["missing"])

    def test_active_screenshot_generation_not_historic_research_seeds(self):
        self.assertEqual(audit.build({}, {}, NOW)["status"],"waiting-for-screenshot")
        self.assertEqual(audit.build({"products":[{"isin":ISIN}]},{},NOW)["total"],0)
        first=audit.build(feed(),{ISIN:provider()},NOW)
        self.assertEqual(first["total"],1)
        self.assertEqual(first["incomplete"],0)
        self.assertNotIn("degiroListed",first["items"][0])
        old=audit.build(feed(),{},NOW)
        second=audit.build(feed(),{},NOW+30000,old)
        third=audit.build(feed(),{},NOW+60000,second)
        self.assertEqual(third["needsHelp"],1)
        self.assertEqual(third["items"][0]["consecutiveChecks"],3)
        healed=audit.build(feed(),{ISIN:provider(NOW+90000)},NOW+90000,third)
        self.assertEqual(healed["needsHelp"],0)
        self.assertEqual(healed["incomplete"],0)
        revised={**feed(),"listUploadedAt":"2026-10-13T08:00:00+00:00"}
        fresh=audit.build(revised,{},NOW+90000,third)
        self.assertEqual(fresh["items"][0]["consecutiveChecks"],1)

    def test_expired_report_never_looks_current(self):
        class Conn:
            def __init__(self,report,stored):
                self.rows=[(report,),(stored,)]
            def execute(self,*args):
                return self
            def fetchone(self):
                return self.rows.pop(0)
        checked=audit.build(feed(),{ISIN:provider()},NOW)
        stale=audit.read(Conn(checked,feed()),NOW+audit.REPORT_MAX_MS+10)
        self.assertEqual(stale["status"],"stale")
        self.assertIsNone(stale["needsHelp"])
        other={**feed(),"listUploadedAt":"2026-10-13T08:00:00+00:00"}
        outdated=audit.read(Conn(checked,other),NOW)
        self.assertEqual(outdated["status"],"checking-new-list")
        self.assertEqual(outdated["items"],[])

    def test_private_routes_and_background_protection(self):
        from pathlib import Path
        scanner=Path("server.py").read_text(encoding="utf-8")
        push=Path("push_server.py").read_text(encoding="utf-8")
        sim=Path("paper_simulation.py").read_text(encoding="utf-8")
        self.assertIn('or path == "/api/degiro/audit"',scanner)
        self.assertIn('if path == "/api/degiro/audit":',scanner)
        self.assertIn('if path == "/product-audit":',push)
        self.assertIn('secrets.compare_digest(supplied, PUSH_SERVICE_TOKEN)',push)
        self.assertIn("degiro_product_audit.store(conn,evidence,quotes,now)",sim)
        self.assertIn("SAVEPOINT bob_degiro_audit",sim)
        self.assertIn("ROLLBACK TO SAVEPOINT bob_degiro_audit",sim)
        self.assertNotIn('degiro_product_audit.read(conn)',scanner)


if __name__=="__main__":
    unittest.main()
