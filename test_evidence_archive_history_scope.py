"""Future-only immutable evaluator metadata in scoped archive; isolated CI.

This is NOT a source replay, production archive run or deletion permission.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
import zipfile

import evidence_archive as archive

HISTORY = frozenset((
    "bob_diagnostic_history", "bob_decision_audit",
    "bob_history_eval_segments", "bob_history_eval_cursor",
))


class HistoryManifestAllowlistTests(unittest.TestCase):
    def test_future_default_backup_includes_both_immutable_eval_tables(self):
        self.assertTrue(HISTORY <= archive.TABLES)
        self.assertTrue(HISTORY <= archive.selected_tables())
        self.assertEqual(archive.VERSION, "bob-evidence-archive-v3")
        for secret_table in ("bob_auth_sessions", "bob_oauth_tokens",
                             "bob_passkeys", "bob_push_subscriptions"):
            self.assertNotIn(secret_table, archive.selected_tables())

    def test_no_automatic_pruning_or_backup_trigger_from_allowlist(self):
        # The data-only allowlist cannot start a worker, wipe source evidence,
        # or imply that an older encrypted ZIP now contains these new tables.
        source = Path(archive.__file__).read_text(encoding="utf-8")
        self.assertNotIn("archive_worker.start(", source)
        self.assertNotIn("DELETE FROM bob_history_eval_segments", source)
        self.assertNotIn("DELETE FROM bob_history_eval_cursor", source)


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Requires isolated PostgreSQL CI database")
class IsolatedFutureSnapshotTests(unittest.TestCase):
    def test_snapshot_contains_sources_and_manifests_without_source_mutation(self):
        import psycopg
        from psycopg import sql
        dsn = os.environ["BOB_TEST_DATABASE_URL"]
        schema = "archive_eval_scope_" + uuid.uuid4().hex
        with psycopg.connect(dsn) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(
                sql.Identifier(schema)))
            admin.execute(sql.SQL("""CREATE TABLE {}.bob_diagnostic_history (
                id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ,
                stage TEXT, payload JSONB)""").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("""CREATE TABLE {}.bob_decision_audit (
                id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ,
                payload JSONB)""").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("""CREATE TABLE {}.bob_history_eval_segments (
                page_sha256 TEXT PRIMARY KEY, area TEXT, first_at TIMESTAMPTZ,
                last_at TIMESTAMPTZ, rows_count INT, categories JSONB,
                outcomes JSONB, source_status TEXT)""").format(sql.Identifier(schema)))
            admin.execute(sql.SQL("""CREATE TABLE {}.bob_history_eval_cursor (
                area TEXT PRIMARY KEY, last_at TIMESTAMPTZ,
                last_id TEXT, processed BIGINT)""").format(sql.Identifier(schema)))
            at = "2026-11-04 10:00:00+00"
            admin.execute(sql.SQL("""INSERT INTO {}.bob_diagnostic_history
                VALUES ('synthetic-original',%s,'input',%s::jsonb)""").format(
                    sql.Identifier(schema)), (at, '{"outcome":"ok"}'))
            admin.execute(sql.SQL("""INSERT INTO {}.bob_decision_audit
                VALUES ('synthetic-decision',%s,%s::jsonb)""").format(
                    sql.Identifier(schema)), (at, '{"direction":"WAIT"}'))
            admin.execute(sql.SQL("""INSERT INTO {}.bob_history_eval_segments
                VALUES (%s,'diagnoses',%s,%s,1,%s::jsonb,%s::jsonb,
                        'sampled-original-not-replayed')""").format(
                    sql.Identifier(schema)), ("a" * 64, at, at,
                                                '{"input":1}', '{"ok":1}'))
            admin.execute(sql.SQL("""INSERT INTO {}.bob_history_eval_cursor
                VALUES ('diagnoses',%s,'synthetic-original',1)""").format(
                    sql.Identifier(schema)), (at,))
        try:
            with tempfile.TemporaryDirectory(prefix="bob-synthetic-eval-") as tmp:
                path = Path(tmp) / "synthetic-only.zip"
                proof = archive.export(dsn, path, tables=set(HISTORY),
                                       schema=schema)
                self.assertEqual(proof["scope"],
                    "reviewed-evidence-tables-not-full-database-backup")
                self.assertFalse(proof["deletionPermitted"])
                self.assertFalse(proof["evidenceDeleted"])
                self.assertEqual({s["name"] for s in proof["tables"]}, HISTORY)
                self.assertTrue(all(s["rows"] == 1 for s in proof["tables"]))
                with zipfile.ZipFile(path) as z:
                    manifest = json.loads(z.read("manifest.json"))
                self.assertEqual({x["name"] for x in manifest["tables"]},
                                 HISTORY)
                self.assertFalse(manifest["restoreVerified"])
                # Isolated test restores only temporary tables and rolls back.
                restored = archive.restore_check(
                    path, proof["sha256"], dsn, temporary_session=True)
                self.assertTrue(restored["restoreVerified"])
                self.assertFalse(restored["deletionPermitted"])
                self.assertEqual(restored["rows"], 4)
            with psycopg.connect(dsn) as conn:
                for name in HISTORY:
                    result = conn.execute(sql.SQL(
                        "SELECT count(*) FROM {}.{}").format(
                            sql.Identifier(schema), sql.Identifier(name)))
                    self.assertEqual(result.fetchone()[0], 1)
        finally:
            with psycopg.connect(dsn) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
