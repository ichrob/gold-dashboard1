"""The research capture must be isolated from order execution and invented evidence."""
import json
import unittest
from unittest.mock import Mock, patch

import zukunft_capture as capture

NOW = 1791813600000  # fixed timestamp for deterministic regression


def fixture():
    market=dict(ready=True, priceFresh=True, price=4000., analysisBarAt=NOW-60000,
                plan=dict(unit="USD/oz"), direction="LONG", score=82.,
                trendContext=dict(available=True, direction="LONG"))
    choice=dict(isin="DE000PJ9NCK0", direction="LONG", scope="XAU/USD",
                approval="Bob-Pflichtprüfung bestanden", koGuardRequired=True)
    quote=dict(isin="DE000PJ9NCK0",currency="EUR",found=True,marketOpen=True,
               bid=1.0,ask=1.02,source="verified-source",
               bidAt=NOW-3000, askAt=NOW-3000)
    return market, dict(choices=[choice]), {choice["isin"]:quote}


class CaptureTests(unittest.TestCase):
    def test_collects_timestamped_verified_observations_without_order_actions(self):
        market, selection, quotes = fixture()
        conn = Mock()
        guard = dict(distancePct=12., source="issuer", termsDate="12.10.2026")
        with patch.object(capture.paper_ko_guard, "assess", return_value=(guard, None)):
            count=capture.record(conn,market,selection,quotes,NOW)
        self.assertEqual(count, 1)
        sql=[c.args[0] for c in conn.execute.call_args_list]
        self.assertTrue(any("bob_zukunft_observations" in s for s in sql))
        self.assertFalse(any("orders" in s.lower() or "execute_trade" in s.lower() for s in sql))
        statement=next(c for c in conn.execute.call_args_list if "INSERT INTO" in c.args[0])
        item=json.loads(statement.args[1][3])
        self.assertEqual(item["side"], "LONG")
        self.assertTrue(item["approved"])
        self.assertAlmostEqual(item["ko_distance_fraction"], .12)
        self.assertEqual(item["quote_source"], "verified-source")
        self.assertEqual(item["source_type"], "observed_product_bid_ask")

    def test_no_paper_change_if_market_uncertain(self):
        market, selection, quotes = fixture()
        market["priceFresh"]=False
        conn=Mock()
        self.assertEqual(capture.record(conn,market,selection,quotes,NOW),0)
        conn.execute.assert_not_called()

    def test_unverified_ko_never_gets_approval(self):
        market, selection, quotes = fixture()
        conn=Mock()
        with patch.object(capture.paper_ko_guard,"assess",return_value=(None,"dated KO missing")):
            self.assertEqual(capture.record(conn,market,selection,quotes,NOW),1)
        statement=next(c for c in conn.execute.call_args_list if "INSERT INTO" in c.args[0])
        item=json.loads(statement.args[1][3])
        self.assertFalse(item["approved"])
        self.assertIsNone(item["ko_distance_fraction"])

    def test_empty_report_does_not_claim_data(self):
        conn=Mock()
        conn.execute.return_value.fetchall.return_value=[]
        data=capture.report(conn)
        self.assertEqual(data["status"],"no_observed_data")
        self.assertFalse(data["realOrders"])
        self.assertEqual(data["instruments"],[])


if __name__=="__main__":
    unittest.main()
