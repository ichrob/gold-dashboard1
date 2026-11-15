"""Isolated-only regression of bounded archived-original page projection check."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
import uuid

import storage_archive_page_replay as page
import storage_history_evaluations as writer


class Snapshot:
    def __init__(self, rows, mode="on", mutate=False):
        self.rows = list(rows)
        self.mode = mode
        self.mutate = mutate
        self.calls = []
        self.answer = None
    def transaction(self):
        return nullcontext()
    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        if sql == "SHOW transaction_read_only":
            self.answer = (self.mode,)
        elif sql.startswith("SET LOCAL "):
            self.answer = None
        elif sql.startswith("SELECT id,recorded_at"):
            lower = (args[0], args[1])
            selected = [row for row in self.rows
                        if (row[1], row[0]) > lower][:args[2]]
            if selected and self.mutate:
                selected = [(selected[0][0], selected[0][1], "tampered", selected[0][3]),
                            *selected[1:]]
            self.answer = selected
        else:
            raise AssertionError("Unexpected query shape")
        return self
    def fetchone(self):
        return self.answer
    def fetchall(self):
        return self.answer


class ArchivePageComparisonTests(unittest.TestCase):
    def setUp(self):
        self.at = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
        self.rows = [
            ("original-1", self.at, "input", "ok"),
            ("original-2", self.at + timedelta(minutes=1), "analysis", "failed"),
            ("original-3", self.at + timedelta(minutes=1), "health", "success"),
            ("original-4", self.at + timedelta(minutes=2), "transport", "error"),
        ]
        self.groups = [self.rows[:2], self.rows[2:]]
        self.manifests = []
        for rows in self.groups:
            s = writer.summarize("diagnoses", rows)
            self.manifests.append((s["digest"], len(rows), s["categories"],
                                   s["outcomes"], rows[0][1], rows[-1][1]))

    def test_two_exact_pages_including_duplicate_clocks(self):
        conn = Snapshot(self.rows)
        result = page.compare(conn, "diagnoses", self.manifests, expected_rows=4)
        self.assertEqual(result["status"], "matching-pages-provenance-unverified")
        self.assertEqual(result["replayedRows"], 4)
        self.assertEqual(result["matchedPages"], 2)
        self.assertFalse(result["fullOriginalReplayVerified"])
        self.assertFalse(result["archiveFileAndBatchBoundVerified"])
        self.assertFalse(result["restoreIsolationVerifiedByThisCheck"])
        self.assertFalse(result["deletionAuthorized"])
        self.assertIsNone(result["physicalBytesFreed"])
        self.assertEqual(sum("SELECT id,recorded_at" in sql for sql, _ in conn.calls), 2)
        self.assertNotIn("original-", json.dumps(result))
        for sql, _ in conn.calls:
            self.assertNotIn("DELETE ", sql.upper())
            self.assertNotIn("UPDATE ", sql.upper())
            self.assertNotIn("INSERT ", sql.upper())

    def test_manifest_or_source_change_denies_page_match(self):
        for conn, manifests in (
            (Snapshot(self.rows, mutate=True), self.manifests),
            (Snapshot(self.rows[:-1]), self.manifests),
            (Snapshot(self.rows), [
                (self.manifests[0][0], self.manifests[0][1],
                 self.manifests[0][2], self.manifests[0][3],
                 self.manifests[0][4] + timedelta(seconds=1),
                 self.manifests[0][5]),
                self.manifests[1]]),
        ):
            result = page.compare(conn, "diagnoses", manifests, expected_rows=4)
            self.assertNotEqual(result["status"], "matching-pages-provenance-unverified")
            self.assertFalse(result["fullOriginalReplayVerified"])

    def test_invalid_budget_and_count_never_touch_source(self):
        for entries, n in (([], 0), (self.manifests, 5),
                           (self.manifests * 10, 40), (self.manifests, True)):
            conn = Snapshot(self.rows)
            result = page.compare(conn, "diagnoses", entries, expected_rows=n)
            self.assertNotEqual(result["status"], "matching-pages-provenance-unverified")
            self.assertEqual(conn.calls, [])
        conn = Snapshot(self.rows)
        self.assertEqual(page.compare(conn, "unrecognized", self.manifests,
                                     expected_rows=4)["status"],
                         "invalid-or-unbounded-request")
        self.assertEqual(conn.calls, [])

    def test_write_session_is_rejected_before_any_source_page(self):
        conn = Snapshot(self.rows, mode="off")
        result = page.compare(conn, "diagnoses", self.manifests, expected_rows=4)
        self.assertEqual(result["status"], "read-only-required")
        self.assertEqual(len(conn.calls), 1)
        self.assertEqual(conn.calls[0][0], "SHOW transaction_read_only")

    def test_truncated_source_and_deadline_fail_closed(self):
        missing = page.compare(Snapshot([]), "diagnoses", self.manifests,
                               expected_rows=4)
        self.assertEqual(missing["status"], "restored-original-page-missing")
        expired = page.compare(Snapshot(self.rows), "diagnoses",
                               self.manifests, expected_rows=4,
                               clock=lambda: 100)
        self.assertEqual(expired["status"], "matching-pages-provenance-unverified")
        times = iter((100, 116))
        expired = page.compare(Snapshot(self.rows), "diagnoses",
                               self.manifests, expected_rows=4,
                               clock=lambda: next(times))
        self.assertEqual(expired["status"], "time-budget-exceeded")

    def test_decisions_keep_direction_and_market_evaluable_labels(self):
        source = [("trade-a", self.at, "LONG", "true"),
                  ("trade-b", self.at + timedelta(seconds=1), "WAIT", "false")]
        summary = writer.summarize("decisions", source)
        manifest = [(summary["digest"], 2, summary["categories"],
                     summary["outcomes"], source[0][1], source[-1][1])]
        result = page.compare(Snapshot(source), "decisions", manifest,
                              expected_rows=2)
        self.assertEqual(result["status"], "matching-pages-provenance-unverified")
        self.assertFalse(result["fullOriginalReplayVerified"])


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Only an isolated CI PostgreSQL database")
class IsolatedPgArchivePageTests(unittest.TestCase):
    def test_originals_remain_untouched_and_readonly(self):
        import psycopg
        from psycopg import sql
        schema = "archive_page_replay_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                admin.execute(sql.SQL("""CREATE TABLE {}.bob_diagnostic_history (
                    id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ NOT NULL,
                    stage TEXT, payload JSONB NOT NULL)""").format(sql.Identifier(schema)))
                recorded = datetime(2026, 11, 1, 10, tzinfo=timezone.utc)
                admin.execute(sql.SQL("""INSERT INTO {}.bob_diagnostic_history
                    VALUES (%s,%s,%s,%s::jsonb),(%s,%s,%s,%s::jsonb)""").format(
                        sql.Identifier(schema)),
                    ("one", recorded, "input", '{"outcome":"ok"}',
                     "two", recorded + timedelta(seconds=1), "health",
                     '{"outcome":"success"}'))
                source = [("one", recorded, "input", "ok"),
                          ("two", recorded + timedelta(seconds=1),
                           "health", "success")]
                summary = writer.summarize("diagnoses", source)
                manifests = [(summary["digest"], summary["rows"],
                              summary["categories"], summary["outcomes"],
                              source[0][1], source[-1][1])]
                with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                        options="-c default_transaction_read_only=on") as reader:
                    reader.execute(sql.SQL("SET search_path TO {}").format(
                        sql.Identifier(schema)))
                    result = page.compare(reader, "diagnoses", manifests,
                                          expected_rows=2)
                    self.assertEqual(result["status"],
                                     "matching-pages-provenance-unverified")
                    self.assertFalse(result["fullOriginalReplayVerified"])
                    self.assertEqual(reader.execute(
                        "SHOW transaction_read_only").fetchone()[0], "on")
                self.assertEqual(admin.execute(sql.SQL(
                    "SELECT count(*) FROM {}.bob_diagnostic_history").format(
                        sql.Identifier(schema))).fetchone()[0], 2)
            finally:
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
