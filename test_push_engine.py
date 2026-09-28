import unittest

from push_engine import PushEngine


class PushEngineTests(unittest.TestCase):
    def test_entry_only_on_direction_transition(self):
        engine = PushEngine(cooldown_seconds=900)
        first = engine.signal_transition("LONG", 82, "LONG", now=1000)
        repeat = engine.signal_transition("LONG", 84, "LONG", now=1060)
        neutral = engine.signal_transition("NEUTRAL", 50, "NEUTRAL", now=1120)
        second = engine.signal_transition("SHORT", 18, "SHORT", now=1180)
        self.assertEqual(first.kind, "entry")
        self.assertIsNone(repeat)
        self.assertIsNone(neutral)
        self.assertEqual(second.kind, "entry")

    def test_stop_updates_are_deduplicated(self):
        engine = PushEngine(cooldown_seconds=900)
        first = engine.stop_update("LONG", 4200.0, 4210.0, now=1000)
        repeat = engine.stop_update("LONG", 4210.0, 4210.0, now=1060)
        changed = engine.stop_update("LONG", 4210.0, 4220.0, now=1120)
        self.assertEqual(first.kind, "stop")
        self.assertIsNone(repeat)
        self.assertEqual(changed.kind, "stop")

    def test_risk_alert_cooldown(self):
        engine = PushEngine(cooldown_seconds=900)
        first = engine.risk_alert("LONG", 4212.0, 4200.0, now=1000)
        repeat = engine.risk_alert("LONG", 4210.0, 4200.0, now=1100)
        later = engine.risk_alert("LONG", 4205.0, 4200.0, now=2000)
        self.assertEqual(first.kind, "risk")
        self.assertIsNone(repeat)
        self.assertEqual(later.kind, "risk")

    def test_exit_is_an_explicit_event(self):
        engine = PushEngine(cooldown_seconds=900)
        event = engine.trade_exit("SHORT", "Signal ungültig", now=1000)
        repeat = engine.trade_exit("SHORT", "Signal ungültig", now=1100)
        self.assertEqual(event.kind, "exit")
        self.assertIsNone(repeat)


if __name__ == "__main__":
    unittest.main()
