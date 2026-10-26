"""Safety regression for one-picture DEGIRO candidate admission."""
import copy
import json
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import Mock

import broker_candidate_evidence as service

ZONE = ZoneInfo("Europe/Zurich")
ISIN = "DE000FG7Q3A9"
OTHER = "DE000FG8NHQ3"
NOW = datetime(2026, 10, 20, 10, 30, tzinfo=ZONE)


def payload(isin=ISIN, time="20.10.2026 10:15"):
    return {
        "isin": isin, "venue": "Société Générale OTC", "currency": "EUR",
        "sourceTime": time, "source": "DEGIRO-Produktdetail",
        "brokerDisplayConfirmed": True, "isExecutableQuote": False,
        "orderWindowVerified": False, "orderSubmitted": False,
        "executionGuaranteed": False,
        "imageSha256": "f" * 64,
        "imageBytes": 180000, "imageMime": "image/png",
        "bid": 5.1, "ask": 5.12
    }


class Memory:
    def __init__(self):
        self.rows = {}
        self.queries = []
        self.fetchone_result = None
        self.fetchall_result = None

    def execute(self, sql, args=()):
        self.queries.append((sql, args))
        if "CREATE TABLE" in sql:
            self.fetchone_result = None
        elif sql.startswith("SELECT payload") and "WHERE isin" in sql:
            self.fetchone_result = (copy.deepcopy(self.rows[args[0]]),) if args[0] in self.rows else None
        elif sql.startswith("INSERT INTO bob_degiro_candidate_proofs"):
            self.rows[args[0]] = json.loads(args[1])
            self.fetchone_result = None
        elif sql.startswith("DELETE FROM bob_degiro_candidate_proofs"):
            keep = sorted(self.rows, key=lambda k: self.rows[k]["observedAt"], reverse=True)[:args[0]]
            self.rows = {k:self.rows[k] for k in keep}
            self.fetchone_result = None
        elif sql.startswith("SELECT payload") and "ORDER BY observed_at" in sql:
            values = sorted(self.rows.values(), key=lambda p:p["observedAt"], reverse=True)
            self.fetchall_result = [(copy.deepcopy(p),) for p in values[:args[0]]]
        else:
            raise AssertionError("Unexpected SQL statement: " + sql)
        return self

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result


class CandidateProofTests(unittest.TestCase):
    def test_model_requires_observed_same_day_and_no_executions(self):
        record = service.validate(payload(), NOW)
        self.assertEqual(record["isin"], ISIN)
        self.assertEqual(record["source"], "Nutzerbild · DEGIRO-Produktdetail")
        self.assertEqual(record["validUntil"], "2026-10-20T22:00:00+02:00")
        self.assertFalse(record["tradeApproved"])
        self.assertFalse(record["rankingsEligible"])
        self.assertFalse(record["isExecutableQuote"])
        self.assertFalse(record["executionConfirmed"])
        self.assertTrue(service.current(record, NOW))
        self.assertFalse(service.current(record, datetime(2026, 10, 20, 22, 0,tzinfo=ZONE)))
        self.assertFalse(service.current(record, datetime(2026, 10, 21, 9, 0,tzinfo=ZONE)))

    def test_invalid_or_wrong_screenshot_rejected(self):
        variants = [
            dict(isin="WRONG"),dict(venue="unbekannt"),dict(currency="USD"),
            dict(sourceTime="19.10.2026 20:15"), dict(sourceTime="20.10.2026 11:15"),
            dict(sourceTime="20.10.2026"), dict(sourceTime="2026-10-20T10:15"),
            dict(source="Emittent"),dict(brokerDisplayConfirmed=False),
            dict(isExecutableQuote=True),dict(orderSubmitted=True),
            dict(imageSha256="a"),dict(imageMime="text/html"),
            dict(imageBytes=12000001),dict(bid=6,ask=5),
            dict(bid=None,ask=5),dict(bid=float("nan")),
        ]
        for update in variants:
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    service.validate({**payload(),**update}, NOW)

    def test_only_same_day_and_clear_timezone(self):
        with self.assertRaises(ValueError):
            service.validate(payload(time="19.10.2026 09:10"),NOW)
        with self.assertRaises(ValueError):
            service.validate(payload(time="20.10.2026 10:31"),NOW)
        with self.assertRaises(ValueError):
            service.validate(payload(time="25.10.2026 02:30"),
                             datetime(2026,10,25,3,0,tzinfo=ZONE))
        self.assertTrue(service.current(service.validate(payload(time="20.10.2026 10:00"),NOW),NOW))

    def test_store_read_reuses_source_clock_and_never_mutates_active_products(self):
        conn = Memory()
        service.init(conn)
        first = service.save(conn,payload(),NOW)
        self.assertTrue(first["ok"])
        self.assertFalse(first["ordersEnabled"])
        self.assertFalse(first["rankingsEligible"])
        self.assertEqual(set(conn.rows),{ISIN})
        self.assertFalse(any("bob_paper_products" in sql for sql,_ in conn.queries))
        report = service.report(conn,NOW)
        self.assertEqual(report["status"],"ok")
        self.assertEqual(report["items"][0]["isin"],ISIN)
        self.assertTrue(report["items"][0]["listingConfirmed"])
        self.assertFalse(report["items"][0]["tradeApproved"])
        older = service.save(conn,payload(time="20.10.2026 10:10"),NOW)
        self.assertTrue(older["preserved"])
        self.assertEqual(conn.rows[ISIN]["observedMinute"],"2026-10-20T10:15")
        with self.assertRaises(ValueError):
            service.save(conn,{**payload(), "venue":"Different OTC"},NOW)
        stale = service.report(conn,datetime(2026,10,20,22,1,tzinfo=ZONE))
        self.assertEqual(len(stale["items"]),1)
        self.assertFalse(stale["items"][0]["listingConfirmed"])
        self.assertEqual(stale["items"][0]["observedMinute"],"2026-10-20T10:15")

    def test_today_listing_can_survive_but_display_quote_expires(self):
        from datetime import timedelta
        conn=Memory()
        service.save(conn,payload(time="20.10.2026 10:30"),NOW)
        current=service.report(conn,NOW)["items"][0]
        self.assertTrue(current["listingConfirmed"])
        self.assertTrue(current["brokerDisplayRecent"])
        self.assertEqual(current["displayClockRole"],"screen-minute-not-quote-source-clock")
        for flag in ("brokerTradabilityNowVerified","executionQuoteVerified",
                     "isExecutableQuote","tradeApproved"):
            self.assertIs(current[flag],False)
        later=service.report(conn,NOW+timedelta(seconds=91))["items"][0]
        self.assertTrue(later["listingConfirmed"])
        self.assertFalse(later["brokerDisplayRecent"])
        self.assertEqual(later["observedAt"],current["observedAt"])
        self.assertFalse(later["executionQuoteVerified"])
        after_close=service.report(conn,NOW+timedelta(hours=12))["items"][0]
        self.assertFalse(after_close["listingConfirmed"])
        self.assertFalse(after_close["brokerDisplayRecent"])

    def test_different_instruments_bound_to_distinct_images(self):
        conn=Memory()
        service.save(conn,payload(),NOW)
        service.save(conn,{**payload(OTHER,time="20.10.2026 10:17"),
            "imageSha256":"e"*64},NOW)
        report=service.report(conn,NOW)
        self.assertEqual({x["isin"] for x in report["items"]},{ISIN,OTHER})
        self.assertTrue(all(x["executionConfirmed"] is False for x in report["items"]))
        self.assertEqual(len(conn.rows),2)


if __name__=="__main__":
    unittest.main()
