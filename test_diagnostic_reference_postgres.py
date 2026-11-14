"""Physical TEMP allocation experiment; synthetic CI data, no live writer.

Extends diagnostic_reference_shadow's logical model with PostgreSQL heap,
TOAST, primary-key and reference-index costs. Not a production schema replica
or a Render savings claim. No original data or DSNs appear in the output.
"""
import hashlib
import json
import os
import unittest
from urllib.parse import urlsplit

from diagnostic_reference_shadow import shadow, _canonical


def synthetic_events(count, unique, width):
    if count not in (32, 128, 256) or unique not in (1, count) or width not in (4, 128):
        raise ValueError("Fixed synthetic experiment matrix only")
    # Stable varied strings prevent long repeated filler from overstating
    # the gain; PostgreSQL still applies its normal JSONB compression.
    payloads = [{"source": "synthetic-only", "values": [
        hashlib.sha256(f"synthetic-{i}-{j}".encode()).hexdigest()
        for j in range(width)]} for i in range(unique)]
    return [{"id": i, "traceId": f"synthetic-trace-{i}",
             "observedAt": 1800000000 + i, "recordedAt": 1800000001 + i,
             "stage": "input", "build": "synthetic-build",
             "payload": payloads[i % unique]} for i in range(count)]


def require_ci_dsn(dsn):
    # Fail before connecting: no Render/restore host, service aliases, query
    # overrides or multi-host DSNs. This test cannot accept original samples.
    parsed = urlsplit(dsn)
    if (parsed.scheme not in ("postgres", "postgresql")
            or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            or parsed.path != "/bob_auth_test" or parsed.query or parsed.fragment):
        raise ValueError("Existing local ephemeral CI database required")


class ReferenceExperimentSafetyTests(unittest.TestCase):
    def test_fixed_matrix_preserves_every_event(self):
        for count in (32, 128, 256):
            for unique in (1, count):
                for width in (4, 128):
                    events = synthetic_events(count, unique, width)
                    result = shadow(events)
                    self.assertEqual(result["originalEvents"], count)
                    self.assertEqual(result["uniquePayloads"], unique)
                    self.assertTrue(result["reconstructionVerified"])
                    self.assertEqual(len({e["traceId"] for e in events}), count)
                    self.assertIsNone(result["physicalBytesFreed"])

    def test_refuses_external_or_overridden_database_before_connect(self):
        for dsn in ("postgresql://host/bob_auth_test",
                    "postgresql://localhost/production",
                    "postgresql://localhost/bob_archive_restore_test",
                    "postgresql://localhost/bob_auth_test?host=external",
                    "host=localhost dbname=bob_auth_test", ""):
            with self.subTest(dsn=dsn), self.assertRaises(ValueError):
                require_ci_dsn(dsn)
        require_ci_dsn("postgresql://localhost/bob_auth_test")

    def test_refuses_unbounded_fixture(self):
        for args in ((257, 1, 4), (32, 2, 4), (32, 1, 1000000)):
            with self.assertRaises(ValueError):
                synthetic_events(*args)


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Existing ephemeral CI PostgreSQL required")
class ReferencePostgresAllocationTests(unittest.TestCase):
    def test_reference_allocation_matrix_and_exact_join_readback(self):
        import psycopg
        dsn = os.environ["BOB_TEST_DATABASE_URL"]
        require_ci_dsn(dsn)
        with psycopg.connect(dsn, connect_timeout=5,
                             options="-c statement_timeout=10000 -c lock_timeout=1000") as conn:
            self.assertEqual(conn.execute("SELECT current_database()").fetchone()[0],
                             "bob_auth_test")
            self.assertEqual(int(conn.execute("SHOW server_version_num").fetchone()[0]) // 10000, 18)
            for count in (32, 128, 256):
                for unique in (1, count):
                    for width in (4, 128):
                        events = synthetic_events(count, unique, width)
                        logical = shadow(events)
                        # Every case rolls back its own TEMP allocations, even
                        # on failure. Never reuse one case's allocated pages.
                        conn.execute("SAVEPOINT reference_case")
                        try:
                            result = self.measure(conn, events)
                            self.assertEqual(result["uniquePayloads"], unique)
                            result.update(rows=count, width=width,
                                          logicalByteDifference=logical["logicalByteDifference"])
                            print("BOB_REFERENCE_PG18 " + json.dumps(result, sort_keys=True))
                        finally:
                            conn.execute("ROLLBACK TO SAVEPOINT reference_case")
                            conn.execute("RELEASE SAVEPOINT reference_case")

    def measure(self, conn, events):
        conn.execute("CREATE TEMP TABLE reference_baseline (id integer PRIMARY KEY, envelope jsonb NOT NULL, payload jsonb NOT NULL)")
        conn.execute("CREATE TEMP TABLE reference_blobs (digest bytea PRIMARY KEY, payload jsonb NOT NULL)")
        conn.execute("CREATE TEMP TABLE reference_events (id integer PRIMARY KEY, envelope jsonb NOT NULL, digest bytea NOT NULL REFERENCES pg_temp.reference_blobs(digest))")
        conn.execute("CREATE INDEX ON pg_temp.reference_events(digest)")
        for event in events:
            payload = _canonical(event["payload"])
            digest = hashlib.sha256(payload).digest()
            envelope = _canonical({k: v for k, v in event.items() if k != "payload"}).decode()
            conn.execute("INSERT INTO pg_temp.reference_baseline VALUES (%s,%s::jsonb,%s::jsonb)",
                         (event["id"], envelope, payload.decode()))
            conn.execute("INSERT INTO pg_temp.reference_blobs VALUES (%s,%s::jsonb) ON CONFLICT DO NOTHING",
                         (digest, payload.decode()))
            stored = conn.execute("SELECT payload FROM pg_temp.reference_blobs WHERE digest=%s", (digest,)).fetchone()[0]
            self.assertEqual(_canonical(stored), payload, "Digest collision or content mismatch")
            conn.execute("INSERT INTO pg_temp.reference_events VALUES (%s,%s::jsonb,%s)",
                         (event["id"], envelope, digest))
        baseline = conn.execute("SELECT id,envelope,payload FROM pg_temp.reference_baseline ORDER BY id").fetchall()
        joined = conn.execute("SELECT e.id,e.envelope,b.payload FROM pg_temp.reference_events e JOIN pg_temp.reference_blobs b USING(digest) ORDER BY e.id").fetchall()
        self.assertEqual(len(joined), len(events))
        self.assertEqual(joined, baseline)
        for event, (row_id, envelope, payload) in zip(events, joined):
            self.assertEqual(row_id, event["id"])
            self.assertEqual(_canonical(dict(envelope, payload=payload)), _canonical(event))
        sizes = {}
        for table in ("reference_baseline", "reference_events", "reference_blobs"):
            total, indexes = conn.execute("SELECT pg_total_relation_size(%s::regclass),pg_indexes_size(%s::regclass)",
                                         ("pg_temp." + table, "pg_temp." + table)).fetchone()
            sizes[table] = {"totalBytes": total, "indexBytes": indexes}
        baseline_bytes = sizes["reference_baseline"]["totalBytes"]
        shared_bytes = sizes["reference_events"]["totalBytes"] + sizes["reference_blobs"]["totalBytes"]
        return {"scope": "synthetic-temp-layout-not-production-or-provider-savings",
                "sizes": sizes, "baselineBytes": baseline_bytes,
                "sharedBytes": shared_bytes, "temporaryByteDifference": baseline_bytes - shared_bytes,
                "uniquePayloads": conn.execute("SELECT count(*) FROM pg_temp.reference_blobs").fetchone()[0],
                "readerEquality": True, "physicalBytesFreed": None}
