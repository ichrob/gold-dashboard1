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
    def test_direct_sg_maturity_condition_is_recognized(self):
        q=provider()
        q['metadata'].pop('maturity')
        q['conditions']={'maturity':dict(value='Open End', conditionVerified=True,
            source='https://www.sg-zertifikate.de/product', reviewedAt=iso(NOW))}
        self.assertNotIn('maturity',audit.examine(feed()['products'][0],q,NOW)['missing'])
        for change in ({'source':None},{'conditionVerified':False},{'value':''},
                       {'revoked':True},{'conflict':True},{'reviewedAt':iso(NOW-28800001)}):
            with self.subTest(change=change):
                import copy
                bad=copy.deepcopy(q);bad['conditions']['maturity'].update(change)
                self.assertIn('maturity',audit.examine(feed()['products'][0],bad,NOW)['missing'])
        q['productVerified']=False
        self.assertIn('maturity',audit.examine(feed()['products'][0],q,NOW)['missing'])

    def test_missing_list_confirmation_is_not_missing_issuer_identity(self):
        p=feed()['products'][0];p.pop('isinConfirmed')
        item=audit.examine(p,provider(),NOW)
        self.assertIn('list-identity',item['missing'])
        self.assertNotIn('identity',item['missing'])
        self.assertFalse(item['tradeApproved'])

    def test_unknown_market_status_is_not_reported_as_closed(self):
        q=provider();q.pop('marketOpen')
        missing=audit.examine(feed()['products'][0],q,NOW)['missing']
        self.assertIn('market-status',missing)
        self.assertNotIn('market-closed',missing)
        q['marketOpen']=False
        self.assertIn('market-closed',audit.examine(feed()['products'][0],q,NOW)['missing'])

    def shared_quote(self):
        q=provider()
        q.pop("leverage");q.pop("leverageAt")
        q.update(found=False,isExecutableQuote=False)
        at=iso(NOW-1000)
        q["chartEvidence"]={"pointAt":at,"bid":6,"ask":6.02,"currency":"EUR"}
        q["issuerLeverageReference"]={"value":18.4,"dated":False,"eligible":False,
                                      "sourceAt":None,"sharedContextAt":at}
        q["sharedTimeContext"]={"at":at,"kind":"issuer-collection","isin":ISIN,
                                "fields":["Referenzhebel"]}
        q["sharedValueObservations"]={"Referenzhebel":{"value":18.4,"contextAt":at,"isin":ISIN}}
        return q

    def test_shared_leverage_agrees_with_cards_without_execution_approval(self):
        q=self.shared_quote()
        item=audit.examine(feed()["products"][0],q,NOW)
        self.assertNotIn("leverage",item["missing"])
        self.assertNotIn("leverage-time",item["missing"])
        self.assertIsNone(item["leverageSourceAt"])
        self.assertTrue(item["leverageObservation"]["current"])
        self.assertIn("quote",item["missing"])
        self.assertFalse(item["tradeApproved"])
        self.assertFalse(item["degiroVerified"])
        stale=audit.examine(feed()["products"][0],q,NOW+300001)
        self.assertNotIn("leverage",stale["missing"])
        self.assertIn("leverage-time",stale["missing"])

    def test_shared_leverage_rejects_mismatched_or_missing_evidence(self):
        cases=[("sharedTimeContext","isin","DE000FG309G0"),
               ("sharedTimeContext","fields",[]),
               ("sharedTimeContext","kind","retrieval"),
               ("issuerLeverageReference","value",None),
               ("issuerLeverageReference","sharedContextAt",iso(NOW)),
               ("issuerLeverageReference","sourceAt",iso(NOW-90001)),
               ("chartEvidence","pointAt",iso(NOW))]
        for group,key,value in cases:
            with self.subTest(group=group,key=key):
                q=self.shared_quote();q[group][key]=value
                item=audit.examine(feed()["products"][0],q,NOW)
                self.assertIn("leverage-time",item["missing"])
                self.assertIsNone(item["leverageObservation"])
                self.assertFalse(item["tradeApproved"])

    def test_complete_issuer_evidence_is_never_degiro_trade_approval(self):
        item=audit.examine(feed()["products"][0],provider(),NOW)
        self.assertEqual(item["missing"],[])
        self.assertEqual(item["state"],"issuer-evidence-complete")
        self.assertFalse(item["degiroVerified"])
        self.assertFalse(item["tradeApproved"])

    def test_sg_swiss_dots_chf_is_not_degiro_quote(self):
        # Confirmed by official Swissquote platform and independent SG product
        # listing: DE000FG8NHQ3 is a CHF Swiss DOTS knock-out warrant.
        isin="DE000FG8NHQ3"
        product={"isin": isin, "productDirection": "SHORT", "isinConfirmed": True}
        quote=provider()
        quote.update(isin=isin,currency="CHF",found=True,
                     priceKind="observed-issuer",isExecutableQuote=True)
        quote["metadata"].update(currency="CHF",issuerExchangeCode="CBSW")
        result=audit.examine(product,quote,NOW)
        self.assertIn("venue",result["missing"])
        self.assertIn("underlying",result["missing"])
        self.assertEqual(result["issuerVenue"],"Swiss DOTS (CHF)")
        self.assertFalse(result["degiroVerified"])
        self.assertFalse(result["tradeApproved"])
        self.assertIn("DEGIRO",result["venueAction"])
        # Only source-validated exact products may carry this conclusion.
        quote["productVerified"]=False
        self.assertNotIn("venue",audit.examine(product,quote,NOW)["missing"])
        # A separate SG Germany EUR product must not inherit Swiss DOTS.
        other=provider()
        other["metadata"]["issuerExchangeCode"]="CBDE"
        self.assertEqual(audit.examine(
            {"isin":ISIN,"productDirection":"SHORT","isinConfirmed":True},
            other,NOW)["missing"],[])

    def test_swiss_dots_not_counted_as_public_recoverable_timestamp_error(self):
        item={"isin":"DE000FG8NHQ3","needsKiHelp":True,
              "missing":["venue","underlying","quote","quote-time","leverage-time"]}
        report={"status":"ok","items":[item]}
        self.assertEqual(audit.public_help_codes(report),[])
        # The private Problem list still explains the venue conflict.
        self.assertIn("Swiss DOTS",audit.CODES["venue"])


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

    def test_read_only_multisource_keeps_original_quote_clocks(self):
        q = provider()
        q["chartEvidence"] = {"bid": 5.98, "ask": 6.01, "currency": "EUR",
                              "pointAt": iso(NOW-15000)}
        q["secondaryQuote"] = {"source": "Stuttgart · unabhängige Beobachtung",
                               "bid": 5.99, "ask": 6.03, "currency": "EUR",
                               "bidAt": iso(NOW-12000), "askAt": iso(NOW-10000)}
        item = audit.examine(feed()["products"][0], q, NOW)
        observations = item["sourceObservations"]
        self.assertEqual(len(observations), 3)
        self.assertTrue(all(x["researchOnly"] and not x["degiroExecutable"] for x in observations))
        self.assertTrue(all(x["current"] for x in observations))
        self.assertEqual(observations[1]["bidAt"], iso(NOW-15000))
        self.assertEqual(observations[1]["askAt"], iso(NOW-15000))
        self.assertFalse(item["tradeApproved"])
        self.assertFalse(item["degiroVerified"])

        # Fetch time and chart age must never manufacture original bid/ask times.
        q["secondaryQuote"].pop("askAt")
        q["chartEvidence"]["pointAt"] = iso(NOW-100000)
        item = audit.examine(feed()["products"][0], q, NOW)
        self.assertEqual(len(item["sourceObservations"]), 2)
        self.assertFalse(item["sourceObservations"][1]["current"])
        self.assertNotIn("researchLinks", {
            k:v for k,v in item.items() if k == "researchLinks" and v
        })
        self.assertFalse(item["tradeApproved"])

    def test_broker_execution_stays_unverified_after_independent_quote_agreement(self):
        q = provider()
        q["chartEvidence"] = {"bid": 6.0, "ask": 6.02,
                              "currency": "EUR", "pointAt": iso(NOW-4000)}
        q["secondaryQuote"] = {"isin": ISIN, "venue": "Stuttgart",
                               "source": "Zweiter autorisierter Anbieter",
                               "bid": 6.01, "ask": 6.03,
                               "currency": "EUR", "bidAt": iso(NOW-6000),
                               "askAt": iso(NOW-3500)}
        item = audit.examine(feed()["products"][0], q, NOW)
        check = item["marketCrossCheck"]
        self.assertTrue(check["checked"])
        self.assertEqual(check["status"], "price-comparable")
        self.assertLess(check["deviationPct"], 1)
        self.assertFalse(check["brokerConnected"])
        self.assertFalse(check["degiroExecutable"])
        self.assertFalse(item["tradeApproved"])
        self.assertFalse(item["degiroVerified"])
        self.assertEqual(item["state"], "issuer-evidence-complete")

    def test_cross_check_rejects_mismatched_identity_venue_source_currency_and_clocks(self):
        q = provider()
        q["secondaryQuote"] = {"isin": "DE000FC1CHB7", "venue": "Stuttgart",
                               "source": "Another provider", "bid": 6.01, "ask": 6.03,
                               "currency": "EUR", "bidAt": iso(NOW-3000),
                               "askAt": iso(NOW-2500)}
        check = audit.examine(feed()["products"][0], q, NOW)["marketCrossCheck"]
        self.assertFalse(check["checked"])
        self.assertIn("ISIN", " ".join(check["reasons"]))
        q["secondaryQuote"]["isin"] = ISIN
        q["secondaryQuote"].pop("venue")
        self.assertFalse(audit.examine(feed()["products"][0], q, NOW)["marketCrossCheck"]["checked"])
        q["secondaryQuote"]["venue"] = "Stuttgart"
        q["secondaryQuote"]["source"] = "SG"
        self.assertFalse(audit.examine(feed()["products"][0], q, NOW)["marketCrossCheck"]["checked"])
        q["secondaryQuote"]["source"] = "Independent"
        q["secondaryQuote"]["currency"] = "CHF"
        self.assertFalse(audit.examine(feed()["products"][0], q, NOW)["marketCrossCheck"]["checked"])
        q["secondaryQuote"]["currency"] = "EUR"
        q["secondaryQuote"]["bidAt"] = iso(NOW-50_000)
        self.assertFalse(audit.examine(feed()["products"][0], q, NOW)["marketCrossCheck"]["checked"])
        q["secondaryQuote"]["bidAt"] = iso(NOW-120_000)
        self.assertFalse(audit.examine(feed()["products"][0], q, NOW)["marketCrossCheck"]["checked"])

    def test_cross_check_outlier_and_no_reuse_of_unverified_identity(self):
        q = provider()
        q["secondaryQuote"] = {"isin": ISIN, "venue": "Stuttgart",
                               "source": "Zweiter Anbieter", "bid": 5.0,
                               "ask": 5.02, "currency": "EUR",
                               "bidAt": iso(NOW-2000), "askAt": iso(NOW-1800)}
        item = audit.examine(feed()["products"][0], q, NOW)
        self.assertEqual(item["marketCrossCheck"]["status"], "outlier")
        self.assertGreater(item["marketCrossCheck"]["deviationPct"], 1)
        self.assertFalse(item["tradeApproved"])
        q["productVerified"] = False
        blocked = audit.examine(feed()["products"][0], q, NOW)
        self.assertEqual(blocked["sourceObservations"], [])
        self.assertFalse(blocked["marketCrossCheck"]["checked"])
        self.assertIn("identity", blocked["missing"])

    def test_known_onvista_link_is_manual_only_and_no_quote(self):
        item = audit.examine({"isin": "DE000FG7N6Z2", "isinConfirmed": True,
                              "productDirection": "LONG"}, {}, NOW)
        self.assertEqual(len(item["researchLinks"]), 1)
        self.assertEqual(item["researchLinks"][0]["mode"], "manual-only")
        self.assertEqual(item["sourceObservations"], [])
        self.assertIn("quote", item["missing"])
        self.assertFalse(item["tradeApproved"])
        self.assertEqual(audit.examine(feed()["products"][0], {}, NOW)["researchLinks"], [])

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

    def test_emitter_terminal_bitmask_blocks(self):
        q=provider()
        q["metadata"]["status"]=9  # SG active bit together with terminal bit
        self.assertIn("terminated",audit.examine(feed()["products"][0],q,NOW)["missing"])

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
