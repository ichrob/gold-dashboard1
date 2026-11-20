import os
import json
import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from aiven_synthetic_scratch_probe import run

URI = "postgresql://test:SECRET@sample.aivencloud.com:12345/defaultdb?sslmode=require"
PROD = "postgresql://render:SECRET@private.render.internal:5432/bob"
PEM = "-----BEGIN CERTIFICATE-----\nQUJDRA==\n-----END CERTIFICATE-----"


class FakeConnection:
    def __init__(self, *, busy=False, count=2):
        self.busy = busy
        self.count = count
        self.sql = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def execute(self, sql):
        self.sql.append(sql)
        return self

    def fetchone(self):
        sql = self.sql[-1]
        if "pg_try_advisory_lock" in sql:
            return (not self.busy,)
        if "count(*)" in sql:
            return (self.count,)
        raise AssertionError("Unexpected SQL")


def capacity_evidence():
    now = datetime.now(timezone.utc) - timedelta(seconds=15)
    stamp = now.isoformat()
    return json.dumps({
        "host": {"source": "aiven-console-host-metrics",
                 "project": "isolated-test", "service": "restore-free", "node": "primary",
                 "observedAt": stamp, "memoryUsedPct": 20, "diskUsedPct": 15},
        "sql": {"status": "observed", "observedAt": stamp,
                "databaseBytes": 9541311, "clientConnections": 1,
                "maxConnections": 20, "idleTransactions": 0,
                "longActiveClients": 0},
        "archive": {"latestVerifiedState": "verified", "verifiedAt": stamp,
                    "restoreVerified": True, "remoteDownloadVerified": True,
                    "encryptionVerified": True, "recoveryKeyVerified": True,
                    "restoreIsolationVerified": True},
    })


def configured(**kwargs):
    return dict({
        "BOB_AIVEN_SYNTHETIC_CHECK": "1",
        "BOB_AIVEN_TEST_DATABASE_URL": URI,
        "BOB_AIVEN_TEST_CA_PEM": PEM,
        "DATABASE_URL": PROD,
        "BOB_AIVEN_CAPACITY_EVIDENCE_JSON": capacity_evidence(),
    }, **kwargs)


class SyntheticScratchTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertEqual(run({})["status"], "disabled")

    def test_no_target_or_certificate_fails_closed(self):
        self.assertEqual(run({"BOB_AIVEN_SYNTHETIC_CHECK": "1"})["status"], "not-configured")
        self.assertEqual(run(configured(BOB_AIVEN_TEST_CA_PEM=""))["status"], "not-configured")

    def test_never_probes_render_or_same_server(self):
        self.assertEqual(run(configured(BOB_AIVEN_TEST_DATABASE_URL=PROD))["status"], "invalid-target")
        self.assertEqual(run(configured(DATABASE_URL=URI))["status"], "target-not-independent")
        self.assertEqual(run(configured(BOB_AIVEN_TEST_DATABASE_URL=URI + "&host=elsewhere"))["status"], "invalid-target")

    def test_success_uses_one_verified_connection_and_rolls_back(self):
        conn = FakeConnection()
        calls = []

        def connect(*a, **kw):
            calls.append((a, kw))
            return conn

        result = run(configured(), connect)
        self.assertEqual(result["status"], "synthetic-scratch-rolled-back")
        self.assertFalse(result["persisted"])
        self.assertTrue(conn.closed)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["sslmode"], "verify-full")
        self.assertEqual(calls[0][1]["connect_timeout"], 5)
        self.assertEqual(conn.sql[0], "BEGIN")
        self.assertTrue(any("CREATE TEMP TABLE" in s for s in conn.sql))
        self.assertTrue(any("pg_try_advisory_lock" in s for s in conn.sql))
        self.assertEqual(conn.sql[-1], "ROLLBACK")
        self.assertFalse(any(s.strip().upper() == "COMMIT" for s in conn.sql))

    def test_busy_restore_does_not_create_table(self):
        conn = FakeConnection(busy=True)
        result = run(configured(), lambda *_a, **_kw: conn)
        self.assertEqual(result["status"], "restore-busy")
        self.assertFalse(any("CREATE" in s for s in conn.sql))
        self.assertEqual(conn.sql[-1], "ROLLBACK")

    def test_failed_verification_does_not_commit(self):
        conn = FakeConnection(count=1)
        result = run(configured(), lambda *_a, **_kw: conn)
        self.assertEqual(result["status"], "scratch-not-confirmed")
        self.assertEqual(conn.sql[-1], "ROLLBACK")

    def test_failure_redacts_endpoint_and_password(self):
        def failed(*_a, **_kw):
            raise RuntimeError("SECRET sample.aivencloud.com")
        result = run(configured(), failed)
        self.assertEqual(result["status"], "connection-or-scratch-not-confirmed")
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("aivencloud", str(result))

    def test_bad_certificate_blocked(self):
        self.assertEqual(run(configured(BOB_AIVEN_TEST_CA_PEM="not a certificate"))["status"],
                         "invalid-certificate")



    def test_missing_host_capacity_evidence_blocks_all_connection_attempts(self):
        calls = []
        def connect(*_a, **_kw):
            calls.append("connected")
            return FakeConnection()
        result = run(configured(BOB_AIVEN_CAPACITY_EVIDENCE_JSON="{}"), connect)
        self.assertEqual(result["status"], "capacity-evidence-unverified")
        self.assertEqual(calls, [])

    def test_broken_evidence_does_not_expose_credential(self):
        result = run(configured(BOB_AIVEN_CAPACITY_EVIDENCE_JSON="{SECRET"))
        self.assertEqual(result["status"], "capacity-evidence-unverified")
        self.assertNotIn("SECRET", str(result))



    def test_api_mode_no_authenticated_host_sample_blocks_before_connect(self):
        calls = []
        def connector(*_a, **_kw):
            calls.append("called")
            return FakeConnection()
        result = run(
            configured(BOB_AIVEN_METRICS_ONCE="1"),
            connector,
            metrics_reader=lambda **_kw: {"status": "not-configured"},
        )
        self.assertEqual(result["status"], "capacity-evidence-unverified")
        self.assertEqual(calls, [])

    def test_api_mode_can_use_recent_provider_sample(self):
        host = {
            "source": "aiven-service-metrics-api",
            "project": "project-ci", "service": "pg-ci",
            "node": "service-wide",
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "memoryUsedPct": 30, "diskUsedPct": 20,
        }
        invoked = []
        def connector(*_a, **_kw):
            invoked.append(True)
            return FakeConnection()
        result = run(
            configured(BOB_AIVEN_METRICS_ONCE="1"),
            connector,
            metrics_reader=lambda **_kw: {"status": "observed", "host": host},
        )
        self.assertEqual(result["status"], "synthetic-scratch-rolled-back")
        self.assertEqual(len(invoked), 1)

    def test_api_pressure_blocks_without_falling_back_to_manual_host(self):
        host = {
            "source": "aiven-service-metrics-api",
            "project": "project-ci", "service": "pg-ci",
            "node": "service-wide",
            "observedAt": datetime.now(timezone.utc).isoformat(),
            "memoryUsedPct": 99, "diskUsedPct": 95,
        }
        invoked = []
        result = run(
            configured(BOB_AIVEN_METRICS_ONCE="1"),
            lambda *_a, **_kw: invoked.append(True),
            metrics_reader=lambda **_kw: {"status": "observed", "host": host},
        )
        self.assertEqual(result["status"], "capacity-evidence-unverified")
        self.assertEqual(invoked, [])

    def test_actual_postgres_temp_table_is_rolled_back_on_isolated_ci(self):
        """Run real SQL only against CI's exact local throwaway test database.

        The injected connector never uses the fake Aiven hostname to connect.
        Missing/ambiguous/local-production configurations skip this test.
        """
        local_url = os.environ.get("BOB_TEST_DATABASE_URL", "")
        parts = urlsplit(local_url)
        if not (parts.scheme in ("postgres", "postgresql")
                and parts.hostname in ("127.0.0.1", "localhost")
                and parts.port == 5432 and parts.path == "/bob_auth_test"):
            self.skipTest("No exact isolated local CI PostgreSQL fixture")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg unavailable in local test runner")

        def local_test_connection(aiven_uri, **kwargs):
            self.assertEqual(aiven_uri, URI)
            self.assertEqual(kwargs["sslmode"], "verify-full")
            return psycopg.connect(
                local_url,
                connect_timeout=kwargs["connect_timeout"],
                autocommit=True, options=kwargs["options"],
                application_name="bob_aiven_synthetic_ci",
            )

        result = run(configured(), local_test_connection)
        self.assertEqual(result["status"], "synthetic-scratch-rolled-back")
        with psycopg.connect(local_url, connect_timeout=5) as verify:
            # A TEMP table created and rolled back must not leave even a
            # transient relation visible after the original session closes.
            found = verify.execute(
                "SELECT count(*) FROM pg_class WHERE relname = "
                "'bob_aiven_synthetic_scratch'"
            ).fetchone()[0]
            self.assertEqual(found, 0)
            acquired = verify.execute(
                "SELECT pg_try_advisory_lock(hashtext('bob_restore_target_v1'))"
            ).fetchone()[0]
            self.assertTrue(acquired)
            verify.execute(
                "SELECT pg_advisory_unlock(hashtext('bob_restore_target_v1'))"
            )



if __name__ == "__main__":
    unittest.main()
