"""Run: python -m unittest -v test_vollautomatisch_engine.py"""
import unittest
import vollautomatisch_engine as engine

SETUP = dict(isin="DE0000000000", side="LONG", score=80,
             approved_product=True, ko_distance_fraction=0.2)


def q(minute, bid, ask=None, age=3):
    return dict(at=f"2026-10-09T08:{minute:02d}:00Z", bid=bid,
                ask=ask if ask is not None else bid+0.02, age_seconds=age)


class PaperEngineTest(unittest.TestCase):
    def test_replay_target_never_real_order(self):
        r = engine.simulate([q(0, 0.99, 1.01), q(1, 1.04, 1.06), q(2, 1.18, 1.20)], SETUP)
        self.assertEqual(r["mode"], "PAPER_ONLY")
        self.assertFalse(r["live_order_capable"])
        self.assertEqual([e["event"] for e in r["events"]].count("BUY_PAPER"), 1)
        self.assertEqual([e["event"] for e in r["events"]].count("SELL_PAPER"), 1)
        self.assertEqual(r["events"][-1]["reason"], "TARGET")
        self.assertGreater(r["equity_eur"], 100)
        self.assertIsNone(r["position"])

    def test_stale_entry_rejected(self):
        r = engine.simulate([q(0, 0.99, 1.01, age=91), q(1, 1.03, 1.05)], SETUP)
        self.assertEqual(r["events"][0]["event"], "BLOCKED")
        self.assertNotIn("BUY_PAPER", [e["event"] for e in r["events"]])

    def test_unapproved_or_neutral_rejected(self):
        for change in ({"approved_product": False}, {"score": 55},
                       {"ko_distance_fraction": 0.01}):
            r = engine.simulate([q(0, 0.99, 1.01)], {**SETUP, **change})
            self.assertEqual(r["events"][0]["event"], "BLOCKED")

    def test_no_duplicate_timestamp(self):
        with self.assertRaises(ValueError):
            engine.simulate([q(0, 0.99, 1.01), q(0, 1.1, 1.12)], SETUP)

    def test_gap_stop_fills_at_bad_available_bid(self):
        r = engine.simulate([q(0, .99, 1.01), q(1, .70, .72)], SETUP)
        self.assertEqual(r["events"][-1]["reason"], "STOP")
        self.assertLess(r["equity_eur"], 100)

    def test_trailing_stop_never_relaxes(self):
        r = engine.simulate([q(0, .99, 1.01), q(1, 1.08, 1.10),
                             q(2, 1.07, 1.09), q(3, 1.00, 1.02)], SETUP)
        trail = [e["stop_eur"] for e in r["events"] if e["event"] == "TRAIL_PAPER"]
        self.assertEqual(trail, sorted(trail))
        self.assertTrue(any(e["event"] == "SELL_PAPER" for e in r["events"]))

    def test_no_budget_trade_when_fees_are_too_high(self):
        r = engine.simulate([q(0, .99, 1.01)], SETUP,
                            {"fee_eur_per_order": 1.0})
        self.assertEqual(r["events"][0]["event"], "BLOCKED")

    def test_adverse_scenarios_have_different_outcomes(self):
        win = engine.demonstration("target")
        loss = engine.demonstration("stop_gap")
        stale = engine.demonstration("stale")
        trailing = engine.demonstration("trailing")
        self.assertGreater(win["equity_eur"], 100)
        self.assertLess(loss["equity_eur"], 100)
        self.assertEqual(stale["equity_eur"], 100)
        self.assertTrue(any(e["event"] == "BLOCKED" for e in stale["events"]))
        self.assertTrue(any(e["event"] == "TRAIL_PAPER" for e in trailing["events"]))
        self.assertTrue(all(r["live_order_capable"] is False
                            for r in (win, loss, stale, trailing)))
        with self.assertRaises(ValueError):
            engine.demonstration("live")

    def test_demo_is_explicitly_synthetic(self):
        r = engine.demonstration()
        self.assertTrue(r["synthetic"])
        self.assertIn("Künstliche", r["notice"])


if __name__ == "__main__":
    unittest.main()
