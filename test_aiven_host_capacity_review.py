import unittest
from datetime import datetime, timedelta, timezone
import aiven_host_capacity_review as a

class AivenHostCapacityTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,13,8,0,tzinfo=timezone.utc)
        self.host={"source":"aiven-console-host-metrics",
                   "observedAt":(self.now-timedelta(seconds=25)).isoformat(),
                   "memoryUsedBytes":700_000_000,"memoryTotalBytes":1_000_000_000,
                   "diskUsedBytes":12_000_000,"diskTotalBytes":1_000_000_000}
        self.sql={"status":"observed","observedAt":self.host["observedAt"],
                  "databaseBytes":9_500_351,"clientConnections":1,"maxConnections":20,
                  "idleTransactions":0,"longActiveClients":0}

    def test_no_host_data_stays_unknown_despite_healthy_sql(self):
        result=a.review(None,self.sql,now=self.now)
        self.assertEqual(result["hostMemoryStatus"],"unverified")
        self.assertEqual(result["oomCause"],"unknown")
        self.assertFalse(result["automaticRestoreAllowed"])
        self.assertIn("host-memory-source-unavailable",result["findings"])

    def test_valid_correlated_host_metrics_no_fabricated_oom(self):
        result=a.review(self.host,self.sql,now=self.now)
        self.assertEqual(result["hostMemoryStatus"],"observed")
        self.assertEqual(result["ramUsedPct"],70.0)
        self.assertEqual(result["dbConnectionUtilizationPct"],5)
        self.assertEqual(result["oomCause"],"unknown")
        self.assertTrue(result["sqlCorrelated"])
        self.assertFalse(result["billingChangeAllowed"])
        self.assertFalse(result["productionMutationAllowed"])

    def test_elevated_and_critical_memory_require_host_evidence(self):
        elevated=a.review({**self.host,"memoryUsedBytes":810_000_000},self.sql,now=self.now)
        self.assertNotIn("elevated-memory-pressure",elevated["findings"])
        critical=a.review({**self.host,"memoryUsedBytes":950_000_000,
                           "diskUsedBytes":900_000_000,
                           "oomLogEvidence":"confirmed"},self.sql,now=self.now)
        self.assertIn("critical-memory-pressure",critical["findings"])
        self.assertIn("elevated-disk-pressure",critical["findings"])
        self.assertIn("oom-confirmed-by-host-log",critical["findings"])
        self.assertEqual(critical["oomCause"],"not-attributed")
        self.assertFalse(critical["automaticRestoreAllowed"])

    def test_bad_clocks_and_values_never_authorize(self):
        for sample in ({**self.host,"observedAt":"2026-11-13T08:00:01Z"},
                       {**self.host,"observedAt":"2026-11-13 07:59:00"},
                       {**self.host,"memoryUsedBytes":-1},
                       {**self.host,"memoryUsedBytes":float("nan")},
                       {**self.host,"memoryUsedBytes":1_500_000_000},
                       {**self.host,"source":"unknown"}):
            with self.subTest(sample=sample):
                result=a.review(sample,self.sql,now=self.now)
                self.assertEqual(result["hostMemoryStatus"],"unverified")
                self.assertFalse(result["automaticRestoreAllowed"])

    def test_unaligned_sql_is_not_correlated(self):
        sql={**self.sql,"observedAt":(self.now-timedelta(hours=1)).isoformat()}
        result=a.review(self.host,sql,now=self.now)
        self.assertFalse(result["sqlCorrelated"])
        self.assertNotIn("databaseBytes",result)
        self.assertIn("sql-time-not-aligned",result["findings"])

class ConsolePercentTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
        self.host = {"source": "aiven-console-host-metrics", "project": "test-project",
                     "service": "test-service", "node": "test-node",
                     "observedAt": self.now.isoformat(), "memoryUsedPct": 70,
                     "diskUsedPct": 12}

    def check(self, pct, previous=None):
        return a.review({**self.host, "memoryUsedPct": pct}, now=self.now,
                        previous_host_sample=previous)

    def test_console_percent_without_invented_bytes(self):
        result = self.check(70)
        self.assertEqual(result["ramUsedPct"], 70)
        self.assertEqual(result["diskUsedPct"], 12)
        self.assertEqual(result["hostMemoryStatus"], "observed")
        self.assertEqual(result["oomCause"], "unknown")

    def test_thresholds_need_two_ordered_samples_except_95(self):
        previous = {**self.host, "observedAt": (self.now-timedelta(hours=1)).isoformat(),
                    "memoryUsedPct": 85}
        for pct in (80, 84.999, 85, 90, 94.999):
            self.assertEqual(self.check(pct)["findings"], [])
        self.assertIn("critical-memory-pressure", self.check(95)["findings"])
        self.assertIn("elevated-memory-pressure", self.check(85, previous)["findings"])
        self.assertEqual(self.check(84.999, previous)["findings"], [])
        for change in ({"memoryUsedPct": 84.9}, {"node": "different"},
                       {"observedAt": self.now.isoformat()},
                       {"observedAt": (self.now+timedelta(seconds=1)).isoformat()},
                       {"observedAt": (self.now-timedelta(hours=3)).isoformat()},
                       {"source": "sql"}, {"memoryUsedPct": True}):
            self.assertNotIn("elevated-memory-pressure",
                             self.check(90, {**previous, **change})["findings"])

    def test_invalid_or_conflicting_percent_is_not_trusted(self):
        for pct in (True, -1, 101, float("nan"), float("inf"), "70"):
            self.assertEqual(self.check(pct)["hostMemoryStatus"], "unverified")
        host = {**self.host, "memoryUsedBytes": 1, "memoryTotalBytes": 2}
        self.assertEqual(a.review(host, now=self.now)["hostMemoryStatus"], "unverified")

    def test_byte_ratio_does_not_round_into_alert(self):
        host = {**self.host, "memoryUsedBytes": 94999, "memoryTotalBytes": 100000}
        del host["memoryUsedPct"]
        self.assertNotIn("critical-memory-pressure", a.review(host, now=self.now)["findings"])

if __name__=="__main__":
    unittest.main()
