"""Real PG18 integration on the EXISTING EPHEMERAL GitHub Actions service.

Never connects to Bob's real Render Postgres or the Restore database; the
CI-supplied BOB_TEST_DATABASE_URL is the temporary workflow service only.
All measurements write exclusively session-local TEMP tables.
"""
import json
import os
import unittest

import storage_jsonb_compression_probe as probe


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Ephemeral CI PostgreSQL integration required")
class TemporaryPgCompressionTests(unittest.TestCase):
    def test_exact_synthetic_jsonb_readback_and_temp_allocations(self):
        import psycopg
        conninfo = os.environ["BOB_TEST_DATABASE_URL"]
        with psycopg.connect(
                conninfo, autocommit=True, connect_timeout=5,
                application_name="bob_ci_synthetic_compression_only",
                options="-c statement_timeout=10000 -c lock_timeout=1000") as conn:
            # Never send test input to a configured production or restore DB.
            dbname = conn.execute("SELECT current_database()").fetchone()[0]
            self.assertEqual(dbname, "bob_auth_test")
            self.assertEqual(conn.execute("SHOW server_version_num").fetchone()[0][:2], "18")
            result = probe.measure_synthetic(conn, probe.fixtures())
            self.assertEqual(result["status"], "isolated-synthetic-probe")
            self.assertTrue(result["readerEquality"])
            self.assertFalse(result["productionRowsChanged"])
            self.assertIsNone(result["physicalBytesFreed"])
            self.assertEqual(result["rows"], 96)
            self.assertEqual(result["methods"]["pglz"]["status"], "verified-synthetic")
            self.assertEqual(result["methods"]["pglz"]["rowsVerified"], 96)
            lz4 = result["methods"]["lz4"]
            self.assertIn(lz4["status"], ("verified-synthetic", "method-unavailable"))
            if lz4["status"] == "verified-synthetic":
                self.assertEqual(lz4["rowsVerified"], 96)
                self.assertIsInstance(result["lz4VersusPglzTemporaryBytes"], int)
            else:
                self.assertIsNone(result["lz4VersusPglzTemporaryBytes"])
            # Fixed nonsecret measurement only; never print raw JSON or DSNs.
            print("BOB_SYNTHETIC_JSONB_PG18 " + json.dumps({
                "status": result["status"],
                "rowsVerified": result["rows"],
                "pglzRelationBytes": result["methods"]["pglz"]["temporaryRelationBytes"],
                "lz4Status": lz4["status"],
                "lz4RelationBytes": lz4.get("temporaryRelationBytes"),
                "lz4MinusPglzBytes": (None if result["lz4VersusPglzTemporaryBytes"] is None
                                      else -result["lz4VersusPglzTemporaryBytes"]),
                "readerEquality": True, "physicalBytesFreed": None,
                "testSource": "ephemeral-github-actions-postgres-18"
            }, sort_keys=True), flush=True)


if __name__ == "__main__":
    unittest.main()
