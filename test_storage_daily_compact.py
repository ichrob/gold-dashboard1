"""Exact daily snapshot and historic projection tests; no production SQL or data changes."""
import json
import unittest

import storage_daily_compact as compact
import storage_brief


class FixedStorageHistoryTests(unittest.TestCase):
    END = 1793728800  # 2026-11-03 18:00 UTC, fixed half-hour slot.
    TABLES = compact.TABLES

    def sample(self, slot, database, values, counters=None):
        return (slot, database, dict(zip(self.TABLES, values)),
                counters if counters is not None else {})

    def counts(self, n):
        return {
            "inserted": n, "updated": n // 2,
            "deleted": n // 4, "hotUpdated": n // 3,
        }

    def test_exact_original_pair_retrospective_and_no_invented_missing_days(self):
        before = self.sample(
            self.END - 86400, 550000000, [100, 200, 300, 400, 500],
            {name: self.counts(100) for name in self.TABLES})
        after = self.sample(
            self.END, 560000000, [110, 270, 330, 360, 570],
            {name: self.counts(120) for name in self.TABLES})
        older = self.sample(
            self.END - 2 * 86400, 530000000, [80, 180, 280, 390, 480])
        source = [after, older, before,
                  (self.END + 1800, 999999999, {"PRIVATE": "must-not-leak"}, {})]
        result = compact.report(source)
        latest = result["latest"]
        self.assertEqual(latest["status"], "observed")
        self.assertEqual(latest["startSlot"], 1793642400)
        self.assertEqual(latest["endSlot"], 1793728800)
        self.assertEqual(latest["databaseBytesDelta"], 10000000)
        self.assertEqual([r["netAllocatedBytes"] for r in latest["tables"]],
                         [10, 70, 30, -40, 70])
        self.assertEqual(latest["tables"][0]["writeCounters"]["inserted"], 20)
        self.assertEqual(result["retrospective"][0]["relationNetBytes"],
                         [10, 70, 30, -40, 70])
        self.assertEqual(result["retrospective"][1]["databaseBytesDelta"],
                         20000000)
        self.assertEqual(result["retrospective"][2]["status"],
                         "missing-baseline-slot")
        self.assertIsNone(result["retrospective"][2]["databaseBytesDelta"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertIsNone(result["diskBytesFreed"])

    def test_counter_reset_and_missing_relations_never_become_zeros(self):
        start = self.sample(self.END - 86400, 2000, [50, 70, 80, 40, 80],
                            {self.TABLES[0]: self.counts(500),
                             self.TABLES[1]: self.counts(10)})
        final = self.sample(self.END, 2200, [60, 80, 90, 40, 90],
                            {self.TABLES[0]: self.counts(20),
                             self.TABLES[1]: self.counts(30)})
        final[2].pop(self.TABLES[4])
        result = compact.report([start, final])
        rows = result["latest"]["tables"]
        self.assertEqual(result["status"], "partial-relations")
        self.assertEqual(rows[0]["counterStatus"], "counter-decrease-reset-or-wrap")
        self.assertIsNone(rows[0]["writeCounters"])
        self.assertEqual(rows[1]["writeCounters"]["inserted"], 20)
        self.assertEqual(rows[2]["counterStatus"], "missing-counter-snapshot")
        self.assertIsNone(rows[4]["netAllocatedBytes"])
        self.assertEqual(result["retrospective"][0]["relationNetBytes"][-1], None)
        self.assertEqual(result["statsResetTimestampStatus"],
                         "not-captured-in-snapshots")

    def test_missing_real_endpoint_and_legacy_empty_counters(self):
        old = self.sample(self.END - 86400, 1000, [1, 2, 3, 4, 5])
        no_end = compact.report([old, (self.END + 300, 2000, {}, {})])
        # Newest accepted slot is yesterday; do not infer tomorrow's endpoint.
        self.assertEqual(no_end["latest"]["status"], "missing-baseline-slot")
        self.assertTrue(all(row is None for row in no_end["retrospective"][0]
                            ["relationNetBytes"]))
        new = self.sample(self.END, 2000, [6, 7, 8, 9, 10])
        comparison = compact.report([old, new])
        self.assertEqual(comparison["latest"]["status"], "observed")
        self.assertTrue(all(row["counterStatus"] == "missing-counter-snapshot"
                            for row in comparison["latest"]["tables"]))

    def test_compact_safe_projection_preserves_fixed_table_order_and_unknowns(self):
        a = self.sample(self.END - 86400, 1000, [10, 20, 30, 40, 50])
        b = self.sample(self.END, 1100, [20, 30, 40, 50, 60])
        source = {
            "status": "observed",
            "fixedSlotDaily": compact.report([a, b]),
            "oauthSecret": "DO-NOT-OUTPUT",
        }
        view = storage_brief.project(source)["fixedSlotDaily"]
        self.assertEqual(view["startSlot"], self.END - 86400)
        self.assertEqual(view["endSlot"], self.END)
        self.assertEqual(view["tableOrder"], list(self.TABLES))
        self.assertEqual(len(view["tables"]), 5)
        self.assertEqual(view["tables"][0]["netAllocated"], 10)
        self.assertEqual(view["retrospectiveDays"][0]["tableDeltas"],
                         [10, 10, 10, 10, 10])
        self.assertEqual(view["retrospectiveDays"][1]["status"],
                         "missing-baseline-slot")
        self.assertIsNone(view["retrospectiveDays"][1]["dbDelta"])
        self.assertFalse(view["statsResetVerified"])
        self.assertIsNone(view["renderVolumeBytesDelta"])
        self.assertIsNone(view["diskBytesFreed"])
        self.assertNotIn("DO-NOT-OUTPUT", json.dumps(view))
        self.assertLess(len(json.dumps(view)), 5500)


if __name__ == "__main__":
    unittest.main()
