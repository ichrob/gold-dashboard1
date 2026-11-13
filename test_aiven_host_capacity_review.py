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
        self.assertIn("elevated-memory-pressure",elevated["findings"])
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

if __name__=="__main__":
    unittest.main()
