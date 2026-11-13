import copy
import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock,patch
import gold_api_history_research as h

START=1794441600  # 2026-11-12 midnight UTC
END=START+86400
NOW=END+3600
AUTH={"BOB_GOLD_API_FREE_HISTORY_ENABLED":"1",
      "BOB_GOLD_API_EXCLUSIVE_ACCOUNT_CONFIRMED":"1","GOLD_API_KEY":"test-key"}

class GoldApiHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.executescript(h.CREATE_SQL)
    def tearDown(self):
        self.db.close()

    def test_free_scope_is_daily_aggregates_or_one_range_ohlc(self):
        self.assertIn("groupBy=day",h.build_request("history-day",START,END,NOW))
        self.assertIn("aggregation=avg",h.build_request("history-day",START,END,NOW))
        self.assertIn("/ohlc/XAU?",h.build_request("ohlc-range",START,END,NOW))
        for mode in ("minute","hour","history-hour","history-minute","ohlc-minute"):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                h.build_request(mode,START,END,NOW)
        for a,b in ((START+1,END),(START,END+1),(START,START),(START,NOW+20)):
            with self.assertRaises(ValueError):
                h.build_request("history-day",a,b,NOW)

    def test_default_fail_closed_never_reads_provider(self):
        network=Mock()
        self.assertEqual(h.run(self.db,"history-day",START,END,environ={},requester=network,now=NOW)["status"],"disabled")
        self.assertEqual(h.run(self.db,"history-day",START,END,
                     environ={"BOB_GOLD_API_FREE_HISTORY_ENABLED":"1"},requester=network,now=NOW)["status"],"account-coordination-unconfirmed")
        self.assertEqual(h.run(self.db,"history-day",START,END,
                     environ={**AUTH,"GOLD_API_KEY":""},requester=network,now=NOW)["status"],"api-key-not-configured")
        network.assert_not_called()
        self.assertEqual(self.db.execute("select count(*) from request_ledger").fetchone()[0],0)

    def test_one_request_persists_raw_daily_and_provenance(self):
        network=Mock(return_value=[{"day":"2026-11-12","avg_price":3980.5}])
        # Explicit mocked history is tied to the actual UTC date.
        result=h.run(self.db,"history-day",START,END,environ=AUTH,requester=network,now=NOW)
        self.assertEqual(result["status"],"stored-research-only")
        self.assertFalse(result["usableAsLiveBar"])
        self.assertFalse(result["usableAsExecutableQuote"])
        self.assertEqual(result["rows"],1)
        self.assertEqual(network.call_args.args[1],"test-key")
        self.assertEqual(self.db.execute("select research_only from historical_originals").fetchone(),(1,))

    def test_ohlc_is_whole_range_not_1m_candles(self):
        obj={"open":4000.0,"high":4040.0,"low":3960.0,"close":4020.0,
             "startTimestamp":START,"endTimestamp":END}
        result=h.run(self.db,"ohlc-range",START,END,
                     environ=AUTH,requester=Mock(return_value=obj),now=NOW)
        self.assertEqual(result["rows"],1)
        self.assertEqual(self.db.execute("select mode from historical_originals").fetchone()[0],"ohlc-range")
        for change in ({"high":3900.0},{"close":None},{"startTimestamp":START+1},
                       {"low":float("nan")}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                h.validate("ohlc-range",{**obj,**change},START,END)

    def test_quota_is_shared_persisted_and_failed_calls_consume_reservation(self):
        network=Mock(side_effect=ValueError("private key must not appear"))
        for i in range(h.MAX_LOCAL_HOURLY):
            self.assertEqual(h.run(self.db,"history-day",START,END,environ=AUTH,
                                   requester=network,now=NOW+i)["status"],"provider-or-validation-failed")
        self.assertEqual(h.run(self.db,"ohlc-range",START,END,environ=AUTH,
                                requester=network,now=NOW+9)["status"],"hourly-reserve-exhausted")
        self.assertEqual(network.call_count,h.MAX_LOCAL_HOURLY)
        self.assertEqual(self.db.execute("select count(*) from request_ledger").fetchone()[0],h.MAX_LOCAL_HOURLY)
        self.assertEqual(h.run(self.db,"ohlc-range",START,END,environ=AUTH,
                               requester=Mock(return_value={"open":1,"high":1,"low":1,"close":1,
                                  "startTimestamp":START,"endTimestamp":END}),now=NOW+3601)["status"],"stored-research-only")

    def test_utc_days_order_duplicates_and_empty_results(self):
        good={"day":"2026-11-12","avg_price":3980.5}
        self.assertEqual(h.validate("history-day",[good],START,END),1)
        for rows in ([],[good,good],[{"day":"2026-11-11","avg_price":3980.5}],
                     [{"day":"2026-11-12","avg_price":"3980.5"}],
                     [{"day":"2026-11-12","avg_price":float("nan")}],
                     [{"day":"2026-11-12","avg_price":-1}]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                h.validate("history-day",rows,START,END)

    def test_endpoint_never_forwards_url_or_key_to_different_host(self):
        with patch.object(h,"build_opener") as opener:
            with self.assertRaises(ValueError):
                h.request_json("https://example.com/history?symbol=XAU","top-secret")
            opener.assert_not_called()

if __name__=="__main__":
    unittest.main()
