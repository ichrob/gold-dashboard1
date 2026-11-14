"""Read-only live cache invalidation without redundant detached OHLC copies."""
import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import server


class LiveCacheReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.now = 1794600000.0
        self.last_closed = int(self.now // 60) * 60000 - 60000
        self.original_spot_at = datetime.fromtimestamp(self.now - 5, timezone.utc).isoformat()
        self.cached = {
            "spots": {"spot_price_as_of": self.original_spot_at, "spot_error": None},
            "history": {"bars_by_tf": {"1m": self.candles(self.last_closed)}},
        }
        for name, value in (
            ("_live_cache", self.cached),
            ("_live_cache_at", self.now - 1),
            ("_technical_history", {}),
            ("LIVE_CACHE_TTL", 30),
        ):
            p = patch.object(server, name, value)
            p.start()
            self.addCleanup(p.stop)

    def candles(self, last_at, count=3, *, instrument="XAU/USD", estimated=False):
        return [
            {
                "openTime": last_at - (count - 1 - index) * 60000,
                "open": 2000.0,
                "high": 2001.0,
                "low": 1999.0,
                "close": 2000.0,
                "isOpen": False,
                "source": "Original dated broker candles",
                "instrument": instrument,
                "estimated": estimated,
            }
            for index in range(count)
        ]

    def test_fresh_newer_spot_history_invalidates_without_copying(self):
        original = self.candles(self.last_closed)
        old_frame = self.candles(self.last_closed - 60000)
        self.cached["history"]["bars_by_tf"]["1m"] = old_frame
        server._technical_history["1m"] = original
        before = copy.deepcopy((self.cached, server._technical_history))
        # The old code cloned every retained candle before merely checking
        # whether the source had a newer completed bar.
        with patch.object(server, "retain_technical_history",
                          side_effect=AssertionError("read-only check copied bars")):
            self.assertFalse(server.live_cache_reusable(now=self.now))
        self.assertEqual((self.cached, server._technical_history), before)

    def test_identical_or_older_history_keeps_valid_spot_cache(self):
        for last in (self.last_closed, self.last_closed - 60000):
            server._technical_history["1m"] = self.candles(last)
            self.assertTrue(server.live_cache_reusable(now=self.now))
        # A genuine same-clock correction remains available to analysis
        # callers, but does not fabricate a newer completed candle.
        correction = self.candles(self.last_closed)
        correction[-1]["high"] += 2
        server._technical_history["1m"] = correction
        self.assertTrue(server.live_cache_reusable(now=self.now))

    def test_stale_or_non_spot_history_never_promotes_into_fresh_cache(self):
        self.cached["history"]["bars_by_tf"]["1m"] = self.candles(self.last_closed - 240000)
        for candidate in (
            self.candles(self.last_closed - 180000),
            self.candles(self.last_closed, instrument="GC=F"),
            self.candles(self.last_closed, estimated=True),
        ):
            server._technical_history["1m"] = candidate
            self.assertTrue(server.live_cache_reusable(now=self.now))

    def test_original_spot_clock_and_error_backoff_are_unchanged(self):
        self.cached["spots"]["spot_price_as_of"] = datetime.fromtimestamp(
            self.now - 31, timezone.utc
        ).isoformat()
        self.assertFalse(server.live_cache_reusable(now=self.now))
        self.cached["spots"]["spot_error"] = "provider unavailable"
        self.assertTrue(server.live_cache_reusable(now=self.now))
        self.cached["spots"]["spot_error"] = None
        self.cached["spots"]["spot_price_as_of"] = self.original_spot_at
        self.assertTrue(server.live_cache_reusable(now=self.now))
        self.assertFalse(server.live_cache_reusable(now=self.now + 31))

    def test_unloaded_frame_does_not_read_or_clone_retained_history(self):
        self.cached["history"]["bars_by_tf"] = {"5m": None}
        server._technical_history["1m"] = self.candles(self.last_closed)
        with patch.object(server, "retain_technical_history",
                          side_effect=AssertionError("unexpected history copy")):
            self.assertTrue(server.live_cache_reusable(now=self.now))


if __name__ == "__main__":
    unittest.main()
