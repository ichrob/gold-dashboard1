"""Regression: all five paper ledgers must advance independently in the background."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import paper_health

TZ = ZoneInfo("Europe/Zurich")


def millis(day, hour, minute):
    return int(datetime(2026,10,day,hour,minute,tzinfo=TZ).timestamp()*1000)


def connection(checked):
    conn = Mock()
    conn.execute.return_value.fetchone.side_effect = [
        ({"checkedAt":x},) if x is not None else ({"status":"scheduled"},)
        for x in checked
    ]
    return conn


class PaperHeartbeatTests(unittest.TestCase):
    def test_all_five_recent_are_really_required(self):
        now = millis(12,9,35)
        conn = connection([now-10_000]*7)
        result = paper_health.snapshot(conn,now)
        self.assertEqual(result["state"],"ok")
        self.assertEqual(result["accountsChecked"],7)
        self.assertEqual(conn.execute.call_count,7)
        self.assertFalse(result["realOrders"])
        self.assertNotIn("isins",result)

    def test_one_stale_or_missing_account_fails_closed(self):
        now=millis(12,9,35)
        for samples in ([now-1000,now-1000,now-301000,now-1000,now-1000,now-1000,now-1000],
                        [now-1000,None,now-1000,now-1000,now-1000,now-1000,now-1000]):
            with self.subTest(samples=samples):
                result=paper_health.snapshot(connection(samples),now)
                self.assertEqual(result["state"],"degraded")

    def test_startup_grace_is_limited_to_first_ten_minutes(self):
        self.assertEqual(paper_health.snapshot(connection([None]*7),millis(12,8,9))["state"],"warming")
        self.assertEqual(paper_health.snapshot(connection([None]*7),millis(12,8,11))["state"],"degraded")

    def test_no_false_failure_outside_scheduled_trading(self):
        for now in (millis(12,7,30),millis(12,22,20),millis(11,15,0)):
            with self.subTest(now=now):
                r=paper_health.snapshot(connection([None]*7),now)
                self.assertEqual(r["state"],"paused")
                self.assertIn(r["sessionMode"], ("night","preparation","weekend"))
                self.assertEqual(r["pauseReason"],"outside-user-trading-window-not-broker-market-closed")

    def test_future_timestamp_does_not_count_as_success(self):
        now=millis(12,12,0)
        self.assertEqual(paper_health.snapshot(connection([now+5000]*7),now)["state"],"degraded")


if __name__=="__main__":
    unittest.main()
