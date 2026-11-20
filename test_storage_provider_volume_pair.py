"""Synthetic-only checks: provider usage, never RAM, relation size or secrets."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

import storage_provider_volume_pair as pair


def provider(at, used, *, source="render-metrics-api", resource=None, unit="bytes"):
    return {"status": "observed", "source": source, "scope": "volume-usage",
            "resource": resource or pair.render_disk_metrics.RESOURCE,
            "unit": unit, "observedAt": at, "diskUsage": used}


class ProviderVolumePairTests(unittest.TestCase):
    def test_before_end_after_requires_distinct_provider_post_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "measurement.json"
            result = pair.before(path, "future-approved-work-1", clock=lambda: 1000,
                                 reporter=lambda: provider(970, 872_000_000))
            self.assertEqual(result["status"], "before-recorded")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertIsNone(result["diskBytesFreedByMaintenance"])
            end = pair.mark_ended(path, clock=lambda: 1050)
            self.assertEqual(end["status"], "end-recorded")
            with self.assertRaises(pair.MeasurementBlocked):
                pair.after(path, clock=lambda: 1070,
                           reporter=lambda: provider(1000, 870_000_000))
            self.assertEqual(pair._load(path)["state"], "ended")
            done = pair.after(path, clock=lambda: 1110,
                              reporter=lambda: provider(1080, 871_000_000))
            self.assertEqual(done["status"], "paired-provider-net-decrease")
            self.assertEqual(done["physicalVolumeNetDecreaseBytes"], 1_000_000)
            self.assertIsNone(done["diskBytesFreedByMaintenance"])
            self.assertEqual(pair._load(path)["after"]["observedAt"], 1080)
            with self.assertRaises(pair.MeasurementBlocked):
                pair.after(path, clock=lambda: 1150,
                           reporter=lambda: provider(1120, 860_000_000))

    def test_increase_is_not_a_freed_bytes_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "volume.json"
            pair.before(path, "normal-maintenance", clock=lambda: 2000,
                        reporter=lambda: provider(1990, 100))
            pair.mark_ended(path, clock=lambda: 2030)
            result = pair.after(path, clock=lambda: 2080,
                                reporter=lambda: provider(2060, 150))
            self.assertEqual(result["physicalVolumeNetDecreaseBytes"], 0)
            self.assertEqual(result["status"], "paired-provider-no-net-decrease")
            self.assertIsNone(result["diskBytesFreedByMaintenance"])

    def test_wrong_source_resource_unit_stale_or_cached_sample_never_counts(self):
        for sample in (provider(990, 100, source="table-size"),
                       provider(990, 100, unit="MB"),
                       provider(990, 100, resource="different-volume"),
                       provider(700, 100),
                       provider(1001, 100),
                       provider(990, True), {"status": "not-observed"}):
            with self.subTest(sample=sample), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "evidence.json"
                with self.assertRaises(pair.MeasurementBlocked):
                    pair.before(path, "safe1", clock=lambda: 1000,
                                reporter=lambda: sample)
                self.assertFalse(path.exists())

    def test_invalid_id_replay_and_insecure_receipt_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            with self.assertRaises(pair.MeasurementBlocked):
                pair.before(path, "unsafe/path", clock=lambda: 1000,
                            reporter=lambda: provider(950, 100))
            pair.before(path, "allowed", clock=lambda: 1000,
                        reporter=lambda: provider(950, 100))
            with self.assertRaises(FileExistsError):
                pair.before(path, "allowed", clock=lambda: 1000,
                            reporter=lambda: provider(950, 100))
            os.chmod(path, 0o644)
            with self.assertRaises(pair.MeasurementBlocked):
                pair.mark_ended(path, clock=lambda: 1020)

    def test_modified_before_snapshot_cannot_be_used_as_provider_proof(self):
        for field, value in (("source", "ram-metric"),
                             ("usedBytes", "870000000"),
                             ("observedAt", 600),
                             ("capturedAt", 1200),
                             ("unit", "MB")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "receipt.json"
                pair.before(path, "validated", clock=lambda: 1000,
                            reporter=lambda: provider(980, 872_000_000))
                record = json.loads(path.read_text())
                record["before"][field] = value
                path.write_text(json.dumps(record))
                with self.assertRaises(pair.MeasurementBlocked):
                    pair.mark_ended(path, clock=lambda: 1020)

    def test_modified_paired_receipt_cannot_claim_impossible_decrease(self):
        for field, value in (("physicalVolumeNetDecreaseBytes", 999_999_999),
                             ("diskBytesFreedByMaintenance", 1)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "receipt.json"
                pair.before(path, "verified-pair", clock=lambda: 1000,
                            reporter=lambda: provider(980, 872_000_000))
                pair.mark_ended(path, clock=lambda: 1030)
                pair.after(path, clock=lambda: 1080,
                           reporter=lambda: provider(1060, 871_000_000))
                record = json.loads(path.read_text())
                record[field] = value
                path.write_text(json.dumps(record))
                with self.assertRaises(pair.MeasurementBlocked):
                    pair._load(path)

    def test_modified_ended_boundary_and_snapshot_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            pair.before(path, "end-boundary", clock=lambda: 1000,
                        reporter=lambda: provider(980, 872_000_000))
            pair.mark_ended(path, clock=lambda: 1030)
            record = json.loads(path.read_text())
            record["maintenanceEndedAt"] = 9000
            path.write_text(json.dumps(record))
            with self.assertRaises(pair.MeasurementBlocked):
                pair.after(path, clock=lambda: 9050,
                           reporter=lambda: provider(9040, 871_000_000))

    def test_without_provider_observation_no_receipt_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            with self.assertRaises(pair.MeasurementBlocked):
                pair.before(path, "missing", clock=lambda: 1000,
                            reporter=lambda: {"status": "configuration-required"})
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
