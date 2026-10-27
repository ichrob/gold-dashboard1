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
    def test_all_sources_and_native_chart_survive_reporting(self):
        q=provider()
        q['chartEvidence']=dict(bid=6,ask=6.02,currency='EUR',pointAt=iso(NOW-80000))
        q['nativeChartEvidence']=dict(bid=7,ask=7.02,currency='CHF',pointAt=iso(NOW-1000))
        for key,source in [('secondaryQuote','comdirect'),('thirdQuote','Swissquote')]:
            q[key]=dict(isin=ISIN,bid=7,ask=7.02,currency='CHF',source=source,
                        bidAt=iso(NOW-1000),askAt=iso(NOW-1000),venue='Swiss DOTS')
        rows=audit.examine(feed()['products'][0],q,NOW)['sourceObservations']
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[-1]['source'],'Swissquote')
        self.assertEqual(rows[1]['currency'],'CHF')
        self.assertEqual(rows[1]['bidAt'],iso(NOW-1000))
        self.assertTrue(all(not row['degiroExecutable'] for row in rows))

    def test_changing_clock_does_not_clear_persistent_quote_problem(self):
        report = None
        for index in range(4):
            q = provider()
            q['found'] = False
            if index % 2:
                q.pop('leverageAt')
            report = audit.build(feed(), {ISIN:q}, NOW, report)
        self.assertIn('product-quote-evidence-missing', audit.public_help_codes(report))
        self.assertNotIn('product-leverage-clock-missing', audit.public_help_codes(report))
        self.assertEqual(report['items'][0]['missingChecks']['quote'], 4)
        # A genuinely recovered quote clears, even while another fault remains.
        q = provider(); q.pop('leverageAt')
        healed = audit.build(feed(), {ISIN:q}, NOW, report)
        self.assertNotIn('product-quote-evidence-missing', audit.public_help_codes(healed))
        self.assertFalse(healed['items'][0]['tradeApproved'])

    def test_recent_matching_issuer_leverage_survives_one_fallback_cycle(self):
        report = audit.build(feed(), {ISIN:provider()}, NOW)
        original_at = report["items"][0]["leverageSourceAt"]
        self.assertEqual(report["items"][0]["issuerLeverageObservation"]["at"], original_at)

        fallback = provider(NOW+60_000)
        fallback.pop("leverageAt")
        fallback["source"] = "comdirect · BNP LiveTrading"
        retained = audit.build(feed(), {ISIN:fallback}, NOW+60_000, report)
        item = retained["items"][0]
        self.assertNotIn("leverage-time", item["missing"])
        self.assertEqual(item["leverageSourceAt"], original_at)
        self.assertEqual(item['timeEvidence']['leverageBasis'], 'original-issuer-time')
        self.assertNotIn('leverage-time', item['timeEvidence']['missing'])
        self.assertFalse(item["tradeApproved"])

        changed = dict(fallback, leverage=19.0)
        self.assertIn("leverage-time", audit.build(
            feed(), {ISIN:changed}, NOW+60_000, report)["items"][0]["missing"])
        expired = provider(NOW+91_000)
        expired.pop("leverageAt")
        self.assertIn("leverage-time", audit.build(
            feed(), {ISIN:expired}, NOW+91_000, report)["items"][0]["missing"])

    def test_legacy_escalation_survives_changed_missing_fields(self):
        q = provider(); q['found'] = False
        report = audit.build(feed(), {ISIN:q}, NOW)
        report['items'][0].pop('missingChecks')
        report['items'][0]['consecutiveChecks'] = 3
        q.pop('leverageAt')
        report = audit.build(feed(), {ISIN:q}, NOW, report)
        self.assertIn('product-quote-evidence-missing', audit.public_help_codes(report))
        self.assertNotIn('product-leverage-clock-missing', audit.public_help_codes(report))

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

    def test_issuer_identity_automatically_matches_unconfirmed_list(self):
        p=feed()['products'][0];p.pop('isinConfirmed')
        item=audit.examine(p,provider(),NOW)
        self.assertNotIn('list-identity',item['missing'])
        self.assertEqual(item['identityEvidence'], 'source-matched')
        self.assertNotIn('identity',item['missing'])
        self.assertFalse(item['tradeApproved'])

    def test_current_exact_broker_listing_confirms_list_identity_only(self):
        import broker_venue_evidence
        product={"isin":ISIN,"productDirection":"SHORT","currency":"EUR"}
        listed_feed={"listOrigin":"degiro-screenshot","listUploadedAt":GEN,
                     "products":[product]}
        evidence=broker_venue_evidence.validate(dict(
            isin=ISIN,reviewed=True,venue="Societe Generale OTC",currency="EUR",
            observedMinute="2026-10-13T09:00",imageReference="exact-list-row"),
            listed_feed,datetime.fromtimestamp(NOW/1000,ZoneInfo("UTC")))
        product["brokerVenueEvidence"]=evidence
        item=audit.build(listed_feed,{ISIN:{"isin":ISIN,"productVerified":False}},NOW)["items"][0]
        self.assertNotIn("list-identity",item["missing"])
        self.assertIn("identity",item["missing"])
        self.assertEqual(item["identityEvidence"],"list-confirmed")
        self.assertFalse(item["tradeApproved"])

        wrong_generation=dict(evidence,listUploadedAt="2026-10-12T07:00:00+00:00")
        product["brokerVenueEvidence"]=wrong_generation
        wrong=audit.build(listed_feed,{ISIN:{"isin":ISIN,"productVerified":False}},NOW)["items"][0]
        self.assertIn("list-identity",wrong["missing"])

        product["brokerVenueEvidence"]=evidence
        expired=audit.build(listed_feed,{ISIN:{"isin":ISIN,"productVerified":False}},
                            NOW+13*3600_000)["items"][0]
        self.assertIn("list-identity",expired["missing"])

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
        self.assertEqual(item['timeEvidence']['leverageBasis'], 'shared-issuer-observation')
        self.assertNotIn('leverage-time', item['timeEvidence']['missing'])
        self.assertIn("quote",item["missing"])
        self.assertFalse(item["tradeApproved"])
        self.assertFalse(item["degiroVerified"])
        stale=audit.examine(feed()["products"][0],q,NOW+300001)
        self.assertNotIn("leverage",stale["missing"])
        self.assertIn("leverage-time",stale["missing"])

    def test_current_shared_provider_observation_precedes_calculation(self):
        from unittest.mock import patch
        q=self.shared_quote()
        calculated=dict(value=20,at=iso(NOW-1000),current=True,kind='calculated-gearing')
        with patch('leverage_backup.current_evidence',return_value=calculated):
            row=audit.examine(feed()['products'][0],q,NOW)
        self.assertEqual(row['leverageObservation']['kind'],'shared-issuer-observation')
        self.assertEqual(row['leverageObservation']['value'],18.4)

    def test_chf_conversion_preserves_original_leverage_context(self):
        q=self.shared_quote()
        q['nativeChartEvidence']=dict(q['chartEvidence'], currency='CHF')
        q['chartEvidence']=dict(q['chartEvidence'], pointAt=iso(NOW-30000))
        item=audit.examine(feed()['products'][0],q,NOW)
        self.assertNotIn('leverage-time',item['missing'])
        self.assertFalse(item['tradeApproved'])
        q['nativeChartEvidence']['pointAt']=iso(NOW-5000)
        self.assertIn('leverage-time',audit.examine(feed()['products'][0],q,NOW)['missing'])

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
        self.assertNotIn("underlying",result["missing"])
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

    def test_bob_calculated_leverage_clock_is_not_original_issuer_time(self):
        q=provider()
        q.update(leverageEstimated=True, leverageSource="Bob · berechneter Hebel")
        item=audit.examine(feed()["products"][0], q, NOW)
        self.assertIn("leverage-time", item["missing"])
        self.assertIsNone(item["leverageSourceAt"])
        self.assertFalse(item["tradeApproved"])
        from unittest.mock import patch
        with patch("leverage_backup.current_evidence", return_value=dict(
                kind="calculated-gearing", value=18.4, current=True, at=iso(NOW-3000))):
            item=audit.examine(feed()["products"][0], q, NOW)
        self.assertNotIn("leverage-time", item["missing"])
        self.assertEqual(item["state"], "analysis-evidence-complete")
        self.assertFalse(item["tradeApproved"])
        self.assertEqual(item["leverageObservation"]["kind"], "calculated-gearing")
        self.assertEqual(item['timeEvidence']['leverageBasis'], 'calculated-input-times')
        self.assertIsNone(item["leverageSourceAt"])

    def test_real_calculation_closes_gap_until_inputs_expire(self):
        from leverage_backup import calculate
        q = provider()
        q.update(leverageEstimated=True)
        q['metadata']['simpleNonQuantoTurbo'] = True
        at = iso(NOW-3000)
        basis = dict(price=4000, at=at, underlying='XAU/USD', source='Gold')
        fx = dict(result='success', base='USD', rates={'EUR':.9},
                  data_updated_at=at, effective_at={'EUR':at}, source='live',
                  sources={'EUR':'live'}, market_session='open')
        q['leverageCalculation'] = calculate(q, basis, fx,
            datetime.fromtimestamp(NOW/1000, ZoneInfo('UTC')))
        item = audit.examine(feed()['products'][0], q, NOW)
        self.assertNotIn('leverage-time', item['missing'])
        self.assertEqual(item['state'], 'analysis-evidence-complete')
        self.assertIsNone(item['leverageSourceAt'])
        self.assertFalse(item['tradeApproved'])
        expired = audit.examine(feed()['products'][0], q, NOW+300001)
        self.assertIn('leverage-time', expired['missing'])
        q['leverageCalculation']['value'] *= 2
        self.assertIn('leverage-time', audit.examine(feed()['products'][0], q, NOW)['missing'])

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

    def test_verified_factor_does_not_request_missing_live_times_or_fake_recovery(self):
        old=audit.build(feed(), {ISIN:{}}, NOW)
        for key in ('type','productType'):
            q=dict(isin=ISIN,productVerified=True,found=False,eligible=False,
                   metadata={key:'FACTOR','status':1,'underlyingType':'FUTURE'})
            report=old
            for n in range(4):report=audit.build(feed(), {ISIN:q}, NOW+n*1000, report)
            item=report['items'][0]
            self.assertEqual(item['state'],'excluded-factor')
            self.assertEqual(item['missing'],['factor'])
            self.assertEqual(item['timeEvidence']['missing'],[])
            self.assertFalse(item['needsKiHelp']);self.assertFalse(item['tradeApproved'])
            self.assertEqual(item['missingChecks'],{})
            self.assertEqual(item['recoveredFields'],[])
            self.assertEqual(report['excluded'],1);self.assertEqual(report['incomplete'],0)
            self.assertEqual(audit.public_help_codes(report),[])
            for bad in (dict(q,productVerified=False),dict(q,isin='DE000FC1CHB7')):
                self.assertNotEqual(audit.examine(feed()['products'][0],bad,NOW)['state'],'excluded-factor')

    def test_emitter_terminal_bitmask_blocks(self):
        q=provider()
        q["metadata"]["status"]=9  # SG active bit together with terminal bit
        self.assertIn("terminated",audit.examine(feed()["products"][0],q,NOW)["missing"])

    def test_terminal_issuer_proof_survives_source_outage_in_same_list(self):
        original=provider()
        original["metadata"].update(status=2,sgStatus=8)
        original.update(found=False,marketOpen=False,leverage=None,leverageAt=None,
                        quoteFailureCode=None)
        first=audit.build(feed(),{ISIN:original},NOW)
        self.assertEqual(first["terminated"],1)
        proof=first["items"][0]["sourceStatusEvidence"]
        self.assertTrue(proof["issuerVerified"])
        self.assertEqual(proof["issuerRawStatus"],8)
        missing=dict(isin=ISIN,productVerified=False,found=False,
                     quoteFailureCode="SG_SOURCE_UNAVAILABLE")
        second=audit.build(feed(),{ISIN:missing},NOW+30000,first)
        item=second["items"][0]
        self.assertEqual(second["terminated"],1)
        self.assertEqual(second["incomplete"],0)
        self.assertEqual(second["needsHelp"],0)
        self.assertEqual(item["missing"],["terminated"])
        self.assertEqual(item["state"],"terminated")
        self.assertTrue(item["sourceStatusEvidence"]["carriedForward"])
        self.assertFalse(item["sourceStatusEvidence"]["currentIssuerAvailable"])
        self.assertEqual(item['timeEvidence'], dict(missing=[], leverageBasis='unavailable', terms={}))
        self.assertEqual(item["sourceStatusEvidence"]["issuerRawStatus"],8)
        self.assertIsNone(item["quoteSourceAt"])
        self.assertIsNone(item["leverageSourceAt"])
        self.assertFalse(item["tradeApproved"])
        self.assertIn("neuer Abruf derzeit nicht verfügbar",item["messages"][0])
        third=audit.build(feed(),{ISIN:missing},NOW+60000,second)
        self.assertEqual(third["items"][0]["missing"],["terminated"])
        # A new day/list generation cannot inherit the old proof.
        revised=dict(feed(),listUploadedAt="2026-10-14T07:00:00+00:00")
        new=audit.build(revised,{ISIN:missing},NOW+60000,third)
        self.assertEqual(new["terminated"],0)
        self.assertEqual(new["incomplete"],1)
        # Confirmed active issuer status is never overridden by the old proof.
        restored=provider(NOW+60000)
        active=audit.build(feed(),{ISIN:restored},NOW+60000,third)
        self.assertEqual(active["terminated"],0)
        self.assertFalse(active["items"][0]["tradeApproved"])

    def test_terminal_carry_requires_original_raw_issuer_terminal_status(self):
        original=provider()
        original["metadata"]["status"]=2
        first=audit.build(feed(),{ISIN:original},NOW)
        second=audit.build(feed(),{ISIN:{"isin":ISIN,"productVerified":False}},
                           NOW+30000,first)
        self.assertEqual(second["terminated"],0)
        self.assertNotIn("carriedForward",second["items"][0]["sourceStatusEvidence"])
        first["items"][0]["sourceStatusEvidence"]["issuerRawStatus"]=8
        first["items"][0]["sourceStatusEvidence"]["issuerVerified"]=False
        second=audit.build(feed(),{ISIN:{"isin":ISIN,"productVerified":False}},
                           NOW+30000,first)
        self.assertEqual(second["terminated"],0)

    def test_verified_ended_product_is_not_a_repair_incident(self):
        q = provider()
        q['metadata']['status'] = 9
        q.update(found=False, marketOpen=False, leverage=None, leverageAt=None)
        report = None
        for _ in range(4):
            report = audit.build(feed(), {ISIN: q}, NOW, report)
        self.assertEqual(report['terminated'], 1)
        self.assertEqual(report['incomplete'], 0)
        self.assertEqual(report['needsHelp'], 0)
        self.assertEqual(report['items'][0]['state'], 'terminated')
        self.assertFalse(report['items'][0]['tradeApproved'])
        self.assertEqual(audit.public_help_codes(report), [])
        # A different product or an unknown status cannot hide missing proof.
        for change in ('identity', 'unknown-status'):
            bad = provider()
            bad['metadata']['status'] = 9 if change == 'identity' else 0
            if change == 'identity':
                bad['isin'] = 'DE000FC1CHB7'
            self.assertNotEqual(audit.examine(feed()['products'][0], bad, NOW)['state'], 'terminated')

    def test_comdirect_inactive_is_explicit_conflict_not_issuer_termination(self):
        q = provider()
        q.update(found=False, marketOpen=None, bid=None, ask=None,
                 leverage=None, leverageAt=None)
        q["comdirectFieldsBackup"] = dict(
            isin=ISIN, state="inactive", inactive=True,
            source="https://www.comdirect.de/inf/zertifikate/"+ISIN,
            checkedAt=iso(NOW))
        item = audit.examine(feed()["products"][0], q, NOW)
        self.assertEqual(item["state"], "incomplete")
        self.assertEqual(item["missing"], ["source-status-conflict"])
        self.assertIsNone(item["dataQuoteSource"])
        self.assertIsNone(item["quoteSourceAt"])
        self.assertFalse(item["sourceStatusEvidence"]["issuerTerminal"])
        self.assertTrue(item["sourceStatusEvidence"]["secondaryInactive"])
        self.assertIn("Quellenkonflikt", item["messages"][0])
        self.assertFalse(item["tradeApproved"])
        # A stale or wrong-product secondary flag must not be promoted.
        for invalid in (dict(isin="DE000FG14AV8"), dict(inactive=False),
                        dict(state="unavailable")):
            bad = dict(q)
            bad["comdirectFieldsBackup"] = dict(q["comdirectFieldsBackup"], **invalid)
            self.assertNotIn("source-status-conflict",
                             audit.examine(feed()["products"][0], bad, NOW)["missing"])

    def test_issuer_confirmed_terminal_has_one_block_without_fake_quote_gaps(self):
        q = provider()
        q["metadata"]["status"] = 2
        q.update(found=False, marketOpen=False, bid=None, ask=None,
                 leverage=None, leverageAt=None)
        q["comdirectFieldsBackup"] = dict(isin=ISIN, state="inactive", inactive=True)
        row = audit.examine(feed()["products"][0], q, NOW)
        self.assertEqual(row["state"], "terminated")
        self.assertEqual(row["missing"], ["terminated"])
        self.assertTrue(row["sourceStatusEvidence"]["issuerTerminal"])
        self.assertFalse(row["sourceStatusEvidence"]["secondaryInactive"])
        self.assertFalse(row["tradeApproved"])

    def test_chf_quote_outage_keeps_source_reason_without_approval(self):
        q = provider()
        q.update(found=False, currency="CHF", marketOpen=None,
                 bid=None, ask=None, leverage=None, leverageAt=None)
        q["metadata"]["currency"] = "CHF"
        q["metadata"]["issuerExchangeCode"] = "CBSW"
        q["swissquoteBackup"] = dict(state="unavailable", reasonCode="HTTP_503")
        row = audit.examine(
            dict(feed()["products"][0], currency="CHF"), q, NOW)
        self.assertEqual(row["sourceStatusEvidence"]["swissquoteState"], "unavailable")
        self.assertEqual(row["sourceStatusEvidence"]["swissquoteReasonCode"], "HTTP_503")
        self.assertIn("quote", row["missing"])
        self.assertFalse(row["tradeApproved"])

    def test_unfinished_or_stale_audit_cannot_certify_recovery(self):
        for state in ('checking-new-list', 'waiting-for-screenshot', 'stale', 'unavailable'):
            self.assertIsNone(audit.public_help_codes({'status': state, 'items': []}))
        self.assertEqual(audit.public_help_codes({'status': 'ok', 'items': []}), [])

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
