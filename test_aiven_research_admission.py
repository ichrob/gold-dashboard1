import unittest
from datetime import datetime, timedelta, timezone
from aiven_research_admission import assess, MAX_SYNTHETIC_BUDGET_BYTES

NOW = datetime(2026, 11, 14, 21, 0, tzinfo=timezone.utc)


def host(**overrides):
    sample = dict(source="aiven-console-host-metrics",
                  project="bob", service="restore-free", node="main",
                  observedAt=(NOW - timedelta(seconds=60)).isoformat(),
                  memoryUsedPct=30.0, diskUsedPct=20.0)
    return {**sample, **overrides}


def sql(**overrides):
    sample = dict(status="observed",
                  observedAt=(NOW - timedelta(seconds=60)).isoformat(),
                  databaseBytes=9541311, clientConnections=1,
                  maxConnections=20, idleTransactions=0, longActiveClients=0)
    return {**sample, **overrides}


def proof(**overrides):
    sample = dict(latestVerifiedState="verified",
                  verifiedAt=(NOW - timedelta(minutes=20)).isoformat(),
                  restoreVerified=True, remoteDownloadVerified=True,
                  encryptionVerified=True, recoveryKeyVerified=True,
                  restoreIsolationVerified=True)
    return {**sample, **overrides}


def evaluate(*, h=None, s=None, p=None, size=200, now=NOW):
    return assess(host() if h is None else h, sql() if s is None else s,
                  proof() if p is None else p, requested_bytes=size, now=now)


class AdmissionTests(unittest.TestCase):
    def test_safe_sample_can_only_be_candidate_not_write_permission(self):
        actual = evaluate()
        self.assertEqual(actual["status"], "candidate-for-manual-synthetic-test-only")
        self.assertTrue(actual["manualReviewOnly"])
        self.assertFalse(actual["automaticDatabaseWritesAllowed"])
        self.assertFalse(actual["productionMigrationAllowed"])
        self.assertFalse(actual["newSpendAllowed"])

    def test_missing_host_metrics_fail_closed(self):
        actual = evaluate(h={})
        self.assertEqual(actual["status"], "blocked")
        self.assertIn("aiven-host-ram-unverified", actual["reasons"])

    def test_missing_real_disk_reading_fail_closed(self):
        data = host()
        del data["diskUsedPct"]
        self.assertIn("aiven-host-disk-unverified", evaluate(h=data)["reasons"])

    def test_inadequate_memory_and_disk_reserve(self):
        actual = evaluate(h=host(memoryUsedPct=75, diskUsedPct=60))
        self.assertIn("aiven-host-ram-reserve-insufficient", actual["reasons"])
        self.assertIn("aiven-host-disk-reserve-insufficient", actual["reasons"])

    def test_stale_host_or_sql_evidence_blocks(self):
        self.assertIn("aiven-host-ram-unverified",
                      evaluate(h=host(observedAt=(NOW-timedelta(hours=2)).isoformat()))["reasons"])
        self.assertIn("aiven-sql-freshness-unverified",
                      evaluate(s=sql(observedAt=(NOW-timedelta(minutes=10)).isoformat()))["reasons"])

    def test_unverified_recovery_or_stale_receipt_blocks(self):
        self.assertIn("independent-recovery-proof-unverified",
                      evaluate(p=proof(restoreVerified=False))["reasons"])
        self.assertIn("independent-recovery-proof-unverified",
                      evaluate(p=proof(verifiedAt=(NOW-timedelta(hours=9)).isoformat()))["reasons"])

    def test_connections_and_idle_transactions_block(self):
        result = evaluate(s=sql(clientConnections=6, idleTransactions=1))
        self.assertIn("aiven-connections-reserve-insufficient", result["reasons"])
        self.assertIn("aiven-query-contention", result["reasons"])

    def test_budget_limit_is_strict(self):
        self.assertIn("synthetic-budget-invalid", evaluate(size=MAX_SYNTHETIC_BUDGET_BYTES+1)["reasons"])
        self.assertIn("synthetic-budget-invalid", evaluate(size=-2)["reasons"])
        self.assertIn("synthetic-budget-invalid", evaluate(size=True)["reasons"])

    def test_unverified_sample_identity_blocks(self):
        self.assertIn("aiven-host-identity-missing", evaluate(h=host(node=""))["reasons"])

    def test_future_and_naive_samples_block(self):
        self.assertIn("aiven-host-ram-unverified",
                      evaluate(h=host(observedAt=(NOW+timedelta(minutes=5)).isoformat()))["reasons"])
        self.assertIn("aiven-sql-freshness-unverified",
                      evaluate(s=sql(observedAt="2026-11-14T20:59:00"))["reasons"])


if __name__ == "__main__":
    unittest.main()
