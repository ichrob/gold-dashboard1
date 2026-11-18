import os
import unittest
from pathlib import Path
from unittest.mock import patch

import legacy_restore_inventory as reader


@unittest.skipUnless(os.getenv("GITHUB_ACTIONS") == "true" and
                     os.getenv("BOB_TEST_DATABASE_URL") ==
                     "postgresql://postgres:ci-test-only@localhost:5432/bob_auth_test",
                     "requires the isolated Bob CI PostgreSQL 18 service")
class LegacyInventoryIntegration(unittest.TestCase):
    def test_provision_count_and_deny_insert(self):
        import psycopg
        from psycopg.conninfo import make_conninfo

        admin_uri = os.environ["BOB_TEST_DATABASE_URL"]
        with psycopg.connect(admin_uri, autocommit=True) as admin:
            admin.execute("CREATE DATABASE bob_archive_restore_test")
            self.addCleanup(self.drop_database, admin_uri)
        target = make_conninfo(admin_uri, dbname=reader.DB_NAME)
        setup = Path(__file__).with_name("scripts") / "provision_legacy_inventory_reader.sql"
        with psycopg.connect(target, autocommit=True) as admin:
            admin.execute("CREATE SCHEMA bob_replay_audit")
            admin.execute("CREATE TABLE bob_replay_audit.cold_checkpoints (id int)")
            admin.execute("INSERT INTO bob_replay_audit.cold_checkpoints VALUES (1),(2)")
            admin.execute("CREATE TABLE public.extra (id int)")
            # Exercise the same role and grants, replacing only psql's interactive
            # password command with a credential confined to the ephemeral CI cluster.
            sql = "\n".join(line for line in setup.read_text().splitlines()
                            if not line.startswith("\\"))
            admin.execute(sql)
            admin.execute("ALTER ROLE bob_legacy_inventory_reader PASSWORD 'ci-reader-only'")
        connect = psycopg.connect

        def local_connection(**kwargs):
            self.assertEqual(kwargs["host"], reader.DB_HOST)
            self.assertEqual(kwargs["sslmode"], "require")
            return connect(**dict(kwargs, host="localhost", sslmode="disable"))

        with patch.dict(os.environ, {reader.PASSWORD_ENV: "ci-reader-only"}), \
                patch.object(psycopg, "connect", side_effect=local_connection):
            result = reader.inventory()
        self.assertEqual(result["status"], "observed", result)
        self.assertEqual(result["knownRows"], {"cold_checkpoints": 2})
        self.assertEqual((result["otherTables"], result["otherRows"]), (1, 0))
        with connect(make_conninfo(target, user=reader.READER, password="ci-reader-only"),
                     autocommit=True) as conn:
            conn.execute("SET default_transaction_read_only = off")
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                conn.execute("INSERT INTO public.extra VALUES (1)")

    @staticmethod
    def drop_database(uri):
        import psycopg
        with psycopg.connect(uri, autocommit=True) as admin:
            admin.execute("DROP DATABASE bob_archive_restore_test")
