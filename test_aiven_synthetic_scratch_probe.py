import unittest
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


def configured(**kwargs):
    return dict({
        "BOB_AIVEN_SYNTHETIC_CHECK": "1",
        "BOB_AIVEN_TEST_DATABASE_URL": URI,
        "BOB_AIVEN_TEST_CA_PEM": PEM,
        "DATABASE_URL": PROD,
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


if __name__ == "__main__":
    unittest.main()
