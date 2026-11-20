"""Synthetic tests only: no production database, Render API, maintenance or keys."""
import copy
import json
import unittest

import storage_maintenance_reserve_evidence as reserve


def samples():
    return {
        "now": 1000,
        "volume": {
            "status": "observed", "source": "render-metrics-api",
            "scope": "volume-usage", "resource": reserve.RESOURCE,
            "unit": "bytes", "observedAt": 980, "diskUsage": 875_000_000,
        },
        "wal": {
            "source": "pg-stat-wal-and-waldir",
            "observedAt": 990, "walDirectoryBytes": 80_000_000,
            "generatedBytesDelta": 20_000_000,
            "statsResetUnchanged": True, "windowSeconds": 30,
        },
        "scratch": {
            "source": "filesystem-free-space-probe", "observedAt": 975,
            "freeBytes": 500_000_000, "sameWorkDirectory": True,
        },
        "locks": {
            "source": "postgres-pg-stat-activity", "observedAt": 985,
            "waitingOnLock": 0, "idleInTransaction": 0, "activeSessions": 4,
        },
        "isolated_workload": {
            "source": "isolated-same-workload-measurement",
            "table": reserve.TARGET,
            "targetTableBytes": 60_000_000,
            "worstCaseWalBytes": 70_000_000,
            "peakScratchBytes": 150_000_000,
            "independentReplayVerified": True,
        },
    }


class ReserveEvidenceTests(unittest.TestCase):
    def test_all_synthetic_inputs_still_never_grant_production_maintenance(self):
        report = reserve.assess(**samples())
        self.assertEqual(report["status"],
                         "operator-evidence-envelope-plausible-not-authorized")
        self.assertEqual(report["conservativeEstimatedPeakBytes"],
                         460_000_000)
        self.assertEqual(report["independentVolumeHeadroomBytes"],
                         reserve.ALLOCATION_BYTES - 875_000_000)
        self.assertFalse(report["readyToExecute"])
        self.assertFalse(report["storageCleanupAuthorized"])
        self.assertFalse(report["providerMaintenanceBeforeAfterPairVerified"])
        self.assertFalse(report["independentActualWALPeakProven"])
        self.assertFalse(report["futureLockAvailabilityProven"])
        self.assertFalse(report["deletionAuthorized"])
        self.assertIsNone(report["physicalBytesFreed"])
        self.assertNotIn("DATABASE_URL", json.dumps(report))

    def test_every_missing_probe_is_explicit_and_fails_closed(self):
        for field in ("volume", "wal", "scratch", "locks", "isolated_workload"):
            data = samples()
            data[field] = None
            result = reserve.assess(**data)
            with self.subTest(missing=field):
                self.assertEqual(result["status"], "evidence-incomplete")
                self.assertTrue(result["missingEvidence"])
                self.assertFalse(result["readyToExecute"])

    def test_ram_table_bytes_or_stale_provider_do_not_replace_volume(self):
        for key, value in (
            ("source", "memory-usage-metric"),
            ("resource", "some-other-service"),
            ("unit", "MiB"),
            ("observedAt", 500),
            ("diskUsage", True),
            ("diskUsage", reserve.ALLOCATION_BYTES),
        ):
            values = samples()
            values["volume"][key] = value
            with self.subTest(key=key, value=value):
                result = reserve.assess(**values)
                self.assertIn("fresh-provider-volume", result["missingEvidence"])

    def test_cumulative_wal_is_not_evidence_of_available_peak_headroom(self):
        for key, value in (
            ("source", "pg-total-database-bytes"),
            ("generatedBytesDelta", -1),
            ("statsResetUnchanged", False),
            ("windowSeconds", 0),
            ("observedAt", 600),
        ):
            values = samples()
            values["wal"][key] = value
            with self.subTest(key=key):
                result = reserve.assess(**values)
                self.assertIn("fresh-wal-counters-and-directory",
                              result["missingEvidence"])
                self.assertFalse(result["independentActualWALPeakProven"])

    def test_scratch_and_lock_observations_are_not_future_guarantees(self):
        data = samples()
        data["scratch"]["sameWorkDirectory"] = False
        self.assertIn("scratch-free-space-at-actual-workdir",
                      reserve.assess(**data)["missingEvidence"])
        data = samples()
        data["locks"]["waitingOnLock"] = 1
        self.assertEqual(reserve.assess(**data)["status"],
                         "lock-contention-observed")
        self.assertFalse(reserve.assess(**data)["futureLockAvailabilityProven"])
        data = samples()
        data["locks"]["idleInTransaction"] = 2
        self.assertEqual(reserve.assess(**data)["status"],
                         "lock-contention-observed")

    def test_fail_closed_on_insufficient_measured_scratch_or_provider_spare(self):
        data = samples()
        data["scratch"]["freeBytes"] = 50_000_000
        self.assertEqual(reserve.assess(**data)["status"],
                         "scratch-envelope-insufficient")
        data = samples()
        data["volume"]["diskUsage"] = reserve.ALLOCATION_BYTES - 200_000_000
        self.assertEqual(reserve.assess(**data)["status"],
                         "provider-capacity-envelope-insufficient")

    def test_unmeasured_isolated_wal_peak_or_original_replay_blocks(self):
        for key, value in (("worstCaseWalBytes", 0),
                           ("peakScratchBytes", None),
                           ("independentReplayVerified", False),
                           ("source", "historical-table-estimate")):
            data = samples()
            data["isolated_workload"][key] = value
            with self.subTest(key=key):
                result = reserve.assess(**data)
                self.assertIn("independently-measured-same-workload-peaks",
                              result["missingEvidence"])
                self.assertFalse(result["readyToExecute"])

    def test_no_side_effects_and_rejected_clock(self):
        data = samples()
        before = copy.deepcopy(data)
        reserve.assess(**data)
        self.assertEqual(data, before)
        data["now"] = float("nan")
        self.assertEqual(reserve.assess(**data)["status"], "invalid-clock")


if __name__ == "__main__":
    unittest.main()
