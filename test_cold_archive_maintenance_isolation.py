"""Archive workers never perform redundant table-tail VACUUM after a scan.

Maintenance is independently scheduled; offload and read-through are unchanged.
"""
import os
import unittest
from unittest.mock import patch

import cold_metrics
import cold_observations


class EndCycle(Exception):
    pass


class ColdArchiveMaintenanceTests(unittest.TestCase):
    def _check(self, module, enabled, no_eligible):
        sleeps = []
        def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps) == 2:
                raise EndCycle()
        with patch.dict(os.environ, {enabled:"1"}), \
             patch.object(module, "_THREAD", None), \
             patch.object(module.threading, "Thread") as thread:
            module.start()
            thread.return_value.start.assert_called_once()
            loop = thread.call_args.kwargs["target"]
        with patch.object(module.time, "sleep", side_effect=sleep), \
             patch.object(module, "run_once", return_value=no_eligible) as run, \
             patch("archive_worker.status", return_value={"status":"idle"}), \
             patch("storage_maintenance.run_once") as maintenance, \
             patch("storage_pressure.delay", return_value=900):
            with self.assertRaises(EndCycle):
                loop()
            run.assert_called_once()
            maintenance.assert_not_called()
        self.assertEqual(len(sleeps), 2)

    def test_metrics_no_eligible_rows_does_not_vacuum(self):
        self._check(cold_metrics, "BOB_COLD_METRIC_ENABLED", {
            "status": "checked",
            "batches": [{"status": "no-eligible-rows", "movedRows": 0}],
        })

    def test_observations_scanned_no_moves_does_not_vacuum(self):
        self._check(cold_observations, "BOB_COLD_OBSERVATIONS_ENABLED", {
            "status": "checked",
            "batches": [{"status": "page-scanned", "scannedRows": 20,
                         "movedRows": 0}],
        })

    def test_archival_success_does_not_run_inline_vacuum(self):
        self._check(cold_metrics, "BOB_COLD_METRIC_ENABLED", {
            "status": "checked",
            "batches": [{"status": "verified-offload",
                         "movedRows": 1, "readThroughVerified": True}],
        })


if __name__ == "__main__":
    unittest.main()
