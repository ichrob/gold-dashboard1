"""Independent history replay is read-only and never licenses deletion."""
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
import uuid

import storage_history_evaluations as writer
import storage_history_replay as replay


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 10, 30, 10, tzinfo=timezone.utc)
        self.diagnoses = [
            ("private-d1", self.at, "input", "ok"),
            ("private-d2", self.at + timedelta(minutes=1), "analysis", "failed"),
        ]
        self.decisions = [
            ("private-a1", self.at, "LONG", "true"),
            ("private-a2", self.at + timedelta(minutes=1), "WAIT", "false"),
        ]

    def test_independent_fingerprint_matches_existing_writer(self):
        for area, rows in (("diagnoses", self.diagnoses),
                           ("decisions", self.decisions)):
            with self.subTest(area=area):
                self.assertEqual(replay.replay_page(area, rows),
                                 writer.summarize(area, rows))
                self.assertNotIn("private-", json.dumps(replay.replay_page(area, rows)))

    def test_manifest_detects_changes_to_order_identity_labels_and_boundaries(self):
        for area, rows in (("diagnoses", self.diagnoses),
                           ("decisions", self.decisions)):
            summary = writer.summarize(area, rows)
            manifest = (summary["digest"], len(rows),
                        summary["categories"], summary["outcomes"],
                        rows[0][1], rows[-1][1])
            self.assertTrue(replay.matches_manifest(area, rows, manifest))
            changed_id = [("different", *rows[0][1:]), rows[1]]
            changed_label = [(*rows[0][:2], "other", rows[0][3]), rows[1]]
            self.assertFalse(replay.matches_manifest(area, changed_id, manifest))
            self.assertFalse(replay.matches_manifest(area, changed_label, manifest))
            self.assertFalse(replay.matches_manifest(
                area, rows, (*manifest[:4], self.at + timedelta(seconds=1), manifest[5])))
            with self.assertRaises(ValueError):
                replay.replay_page(area, [rows[1], rows[0]])

    def test_bounded_sql_reads_without_mutation(self):
        for area in replay.AREAS:
            self.assertIn("ORDER BY recorded_at,id LIMIT %s", replay.SOURCE_SQL[area])
            self.assertIn("ORDER BY recorded_at,id LIMIT 1", replay.TAIL_SQL[area])
            for query in (replay.SOURCE_SQL[area], replay.TAIL_SQL[area]):
                for forbidden in ("DELETE ", "UPDATE ", "INSERT ", "SELECT *"):
                    self.assertNotIn(forbidden, query.upper())
        with self.assertRaises(ValueError):
            replay.replay_page("other", [])
        with self.assertRaises(ValueError):
            replay.replay_page("diagnoses", self.diagnoses * 201)

    def test_replayed_prefix_not_mistaken_for_complete_history(self):
        rows = self.diagnoses
        summary = writer.summarize("diagnoses", rows)
        manifest = (summary["digest"], len(rows), summary["categories"],
                    summary["outcomes"], rows[0][1], rows[-1][1])
        class Fake:
            def __init__(self, changed=False, pending=False):
                self.changed = changed
                self.pending = pending
                self.data = None
                self.sql = []
            def execute(self, sql, params=()):
                self.sql.append(sql)
                if "bob_history_eval_cursor" in sql:
                    self.data = (rows[-1][1], rows[-1][0], len(rows))
                elif "bob_history_eval_segments" in sql:
                    self.data = [manifest]
                elif "SELECT id,recorded_at,stage" in sql:
                    self.data = [("altered", *rows[0][1:]), rows[1]] if self.changed else rows
                elif "SELECT id FROM bob_diagnostic_history" in sql:
                    self.data = ("new-after-cursor",) if self.pending else None
                else:
                    raise AssertionError("Unexpected SQL")
                return self
            def fetchone(self):
                return self.data
            def fetchall(self):
                return self.data
        cutoff = self.at + timedelta(days=3)
        good = Fake()
        result = replay.inspect_area(good, "diagnoses", cutoff)
        self.assertEqual(result["status"], "verified-stable-projection")
        self.assertEqual(result["replayedRows"], 2)
        self.assertEqual(replay.inspect_area(Fake(pending=True),
            "diagnoses", cutoff)["status"], "verified-prefix-catchup-pending")
        self.assertEqual(replay.inspect_area(Fake(changed=True),
            "diagnoses", cutoff)["status"], "source-or-manifest-mismatch")
        self.assertFalse(any("DELETE" in q.upper() or "UPDATE " in q.upper()
                             for q in good.sql))


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Requires isolated PostgreSQL CI database")
class IsolatedDatabaseTests(unittest.TestCase):
    def test_captured_manifests_replay_then_source_change_fails(self):
        import psycopg
        from psycopg import sql
        schema = "history_replay_" + uuid.uuid4().hex
        now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                conn.execute("""CREATE TABLE bob_diagnostic_history(
                    id text PRIMARY KEY, recorded_at timestamptz NOT NULL,
                    stage text, payload jsonb)""")
                conn.execute("""CREATE TABLE bob_decision_audit(
                    id text PRIMARY KEY, recorded_at timestamptz NOT NULL,
                    payload jsonb)""")
                writer.init(conn)
                conn.execute("""INSERT INTO bob_diagnostic_history VALUES
                    ('d1','2026-10-30 10:00+00','input','{"outcome":"ok"}'),
                    ('d2','2026-10-30 10:01+00','analysis','{"outcome":"failed"}')""")
                conn.execute("""INSERT INTO bob_decision_audit VALUES
                    ('a1','2026-10-30 10:00+00','{"direction":"LONG","marketEvaluable":true}'),
                    ('a2','2026-10-30 10:01+00','{"direction":"WAIT","marketEvaluable":false}')""")
                captured = writer.capture(conn, now)
                self.assertEqual(captured["areas"]["diagnoses"], "page-recorded")
                # Use a separate, explicitly read-only session to test the
                # same snapshot contract used in production.
                with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                        options="-c default_transaction_read_only=on") as reader:
                    reader.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                    reader.commit()  # ensure inspect starts a top-level read-only transaction
                    result = replay.inspect(reader, now)
                self.assertEqual(result["status"], "projections-verified-only")
                self.assertFalse(result["fullOriginalReplayVerified"])
                self.assertFalse(result["deletionAuthorized"])
                conn.execute("""UPDATE bob_diagnostic_history
                    SET payload='{"outcome":"failed"}'::jsonb WHERE id='d1'""")
                # An independent subsequent snapshot must detect the change.
                with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                        options="-c default_transaction_read_only=on") as reader:
                    reader.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                    reader.commit()
                    changed = replay.inspect(reader, now)
                self.assertEqual(changed["areas"]["diagnoses"]["status"],
                                 "source-or-manifest-mismatch")
                self.assertEqual(changed["status"], "partial")
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
