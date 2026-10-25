"""A missing diagnostic capture is not a missed market evaluation."""
import json
import unittest

from diagnostic_health_cadence import assess

SHA_A = "a" * 40
SHA_B = "b" * 40


def observation(at, session="trading", build=SHA_A, **extra):
    return {
        "stage": "health", "observedAt": at, "build": build,
        "payload": {"status": "ok", "session": session, **extra},
    }


class CadenceTests(unittest.TestCase):
    def test_trading_archive_gaps_are_review_leads_only(self):
        result = assess([observation(1000), observation(1030),
                         observation(1060), observation(1200)])
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["observedTradingWindowIntervals"], 3)
        self.assertEqual(result["tradingCaptureIntervalsOver90s"], 1)
        self.assertEqual(result["maxTradingCaptureGapSeconds"], 140)
        self.assertFalse(result["workerMissed30sCyclesVerified"])
        self.assertFalse(result["workerStoppedVerified"])
        self.assertFalse(result["realOrders"])
        self.assertEqual(result["latestSession"], "trading")

    def test_weekend_pause_is_not_treated_as_lost_trade_ticks(self):
        result = assess([observation(1000, "weekend"),
                         observation(3000, "weekend"), observation(8000, "weekend")])
        self.assertEqual(result["state"], "outside-trading-window-observation")
        self.assertEqual(result["observedTradingWindowIntervals"], 0)
        self.assertEqual(result["tradingCaptureIntervalsOver90s"], 0)
        self.assertEqual(result["observedNonTradingWindowIntervals"], 2)
        self.assertIsNone(result["maxTradingCaptureGapSeconds"])

    def test_build_and_session_boundaries_are_not_called_worker_gaps(self):
        result = assess([observation(1000, build=SHA_A),
                         observation(2000, build=SHA_B),
                         observation(2010, build=SHA_B),
                         observation(3000, "weekend", SHA_B)])
        self.assertEqual(result["sameBuildSessionIntervals"], 1)
        self.assertEqual(result["crossBuildOrSessionBoundariesSkipped"], 2)
        self.assertEqual(result["tradingCaptureIntervalsOver90s"], 0)

    def test_unknown_missing_or_malformed_stays_unverified(self):
        self.assertEqual(assess([])["status"], "insufficient")
        self.assertEqual(assess([observation(1000)])["status"], "insufficient")
        self.assertEqual(assess([observation(1000, build="unknown"),
                                 observation(2000, build="unknown")])["status"], "insufficient")
        result = assess([observation(1000, session=[]),
                         observation(2000, session="unknown"), # ignored unknown mode
                         {"stage": "push", "observedAt": 3000,
                          "payload": {"token": "DONT-SHOW"}},
                         {"stage": "health", "observedAt": float("nan"),
                          "payload": {"status": "ok"}},
                         {"stage": "health", "observedAt": 4000,
                          "payload": {"session": "trading", "secret": "NEVER-RETURN"}}])
        self.assertEqual(result["status"], "insufficient")
        self.assertNotIn("DONT-SHOW", json.dumps(result))
        self.assertNotIn("NEVER-RETURN", json.dumps(result))
        self.assertFalse(result["workerStoppedVerified"])

    def test_duplicate_clock_not_extra_run_and_only_twenty_samples(self):
        captures = [observation(1000 + i*30) for i in range(30)]
        captures.append(observation(1000 + 29*30))
        r = assess(captures)
        self.assertEqual(r["sampledHealthCaptures"], 20)
        self.assertEqual(r["sameBuildSessionIntervals"], 19)
        self.assertEqual(r["tradingCaptureIntervalsOver90s"], 0)


if __name__ == "__main__":
    unittest.main()
