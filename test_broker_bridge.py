"""Read-only checks for the separate manual and future broker routes."""
import unittest
import broker_bridge


class BrokerSignalTests(unittest.TestCase):
    def test_degiro_is_manual(self):
        result = broker_bridge.route_signal("degiro", "LONG", "DE000FG4JXV7")
        self.assertEqual(result["route"], "DEGIRO_MANUAL_SIGNAL")
        self.assertTrue(result["manualDecisionRequired"])
        self.assertFalse(result["orderSubmitted"])
        self.assertFalse(result["liveOrderEnabled"])

    def test_future_apis_are_unconnected(self):
        for provider in ("ibkr", "ig"):
            result = broker_bridge.route_signal(provider, "SHORT")
            self.assertEqual(result["route"], "API_ADAPTER_NOT_CONNECTED")
            self.assertFalse(result["instrumentMappingVerified"])
            self.assertFalse(result["paperOrderEnabled"])
            self.assertFalse(result["liveOrderEnabled"])

    def test_waiting_and_bad_signals(self):
        for provider in ("degiro", "ibkr", "ig"):
            self.assertEqual(broker_bridge.route_signal(provider, "NEUTRAL")["route"], "NO_ACTION")
        with self.assertRaises(ValueError):
            broker_bridge.route_signal("degiro", "BUY")


if __name__ == "__main__":
    unittest.main()
