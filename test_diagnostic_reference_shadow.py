import copy
import unittest
from diagnostic_reference_shadow import shadow


class DiagnosticReferenceShadowTests(unittest.TestCase):
    def test_equal_payload_distinct_events_round_trip(self):
        events = [
            {"id": 1, "stage": "input", "observedAt": "t1",
             "trace": "a", "payload": {"b": [1, 2], "a": True}},
            {"id": 2, "stage": "input", "observedAt": "t2",
             "trace": "b", "payload": {"a": True, "b": [1, 2]}},
            {"id": 3, "stage": "analysis", "observedAt": "t3",
             "trace": "c", "payload": {"a": False}},
        ]
        before = copy.deepcopy(events)
        result = shadow(events)
        self.assertEqual(events, before)
        self.assertEqual(result["originalEvents"], 3)
        self.assertEqual(result["uniquePayloads"], 2)
        self.assertTrue(result["reconstructionVerified"])
        self.assertFalse(result["originalRowsChanged"])
        self.assertIsNone(result["physicalBytesFreed"])
        self.assertNotIn("trace", result)

    def test_controlled_logical_size_comparison(self):
        payload = {"source": "sample", "values": list(range(100)),
                   "description": "synthetic-data-" * 20}
        events = [{"id": i, "observedAt": str(i), "payload": payload}
                  for i in range(40)]
        result = shadow(events)
        self.assertEqual(result["originalEvents"], 40)
        self.assertEqual(result["uniquePayloads"], 1)
        self.assertTrue(result["reconstructionVerified"])
        self.assertGreater(result["originalLogicalBytes"], 0)
        self.assertEqual(result["logicalByteDifference"],
                         result["originalLogicalBytes"] - result["referenceLogicalBytes"])
        self.assertIsNone(result["physicalBytesFreed"])

    def test_aggregate_size_limit(self):
        events = [{"id": i, "payload": {"text": "x" * 900000}}
                  for i in range(10)]
        with self.assertRaises(ValueError):
            shadow(events)

    def test_empty_and_fail_closed(self):
        self.assertEqual(shadow([])["uniquePayloads"], 0)
        with self.assertRaises(ValueError):
            shadow([{"id": 1}])
        with self.assertRaises(ValueError):
            shadow([{"payload": {"bad": float("nan")}}])
        with self.assertRaises(ValueError):
            shadow([{"payload": 1}] * 257)


if __name__ == "__main__":
    unittest.main()
