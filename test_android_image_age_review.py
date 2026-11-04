"""Two-day DEGIRO hot window, protected evidence and zero-delete regressions."""
import inspect
import os
import unittest
import uuid
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import android_image_age_review as review


class AgeDecisionTests(unittest.TestCase):
    def setUp(self):
        self.local = ZoneInfo("Europe/Zurich")
        self.now = datetime(2026, 11, 4, 18, 0, tzinfo=self.local)

    def row(self, day, stage="read-failed", parsed=False, pointer=False,
            processing_at=None):
        return (datetime(2026, 11, day, 12, 0, tzinfo=self.local),
                stage, parsed, processing_at, pointer)

    def test_today_yesterday_are_hot_vorgestern_is_old(self):
        for day in (3, 4):
            self.assertEqual(review.classify(self.row(day), self.now),
                             "hot-today-or-yesterday")
        self.assertEqual(review.classify(self.row(2), self.now),
                         "review-old-failed-original-for-archive")
        self.assertEqual(review.classify(self.row(1), self.now),
                         "review-old-failed-original-for-archive")

    def test_preserve_references_original_product_proofs_and_active_ocr(self):
        self.assertEqual(review.classify(self.row(1, "synced"), self.now),
                         "preserve-product-proof-or-example")
        self.assertEqual(review.classify(self.row(1, parsed=True), self.now),
                         "preserve-product-proof-or-example")
        self.assertEqual(review.classify(self.row(1, pointer=True), self.now),
                         "preserve-archived-reference")
        self.assertEqual(review.classify(self.row(
            1, processing_at=self.now-timedelta(minutes=20)), self.now),
            "preserve-active-ocr")
        self.assertEqual(review.classify(self.row(1, "reading"), self.now),
                         "preserve-unknown")
        self.assertEqual(review.classify(self.row(1, "superseded"), self.now),
                         "preserve-product-proof-or-example")

    def test_clock_boundary_is_swiss_calendar_not_rolling_48_hours(self):
        local = ZoneInfo("Europe/Zurich")
        now = datetime(2026, 11, 4, 0, 10, tzinfo=local)
        old = (datetime(2026, 11, 2, 23, 59, tzinfo=local),
               "read-failed", False, None, False)
        yesterday = (datetime(2026, 11, 3, 0, 0, tzinfo=local),
                     "read-failed", False, None, False)
        self.assertEqual(review.classify(old, now),
                         "review-old-failed-original-for-archive")
        self.assertEqual(review.classify(yesterday, now),
                         "hot-today-or-yesterday")

    def test_incomplete_or_future_clocks_fail_closed(self):
        self.assertEqual(review.classify((), self.now), "preserve-unknown")
        self.assertEqual(review.classify(
            (self.now+timedelta(days=1), "synced", True, None, False),
            self.now), "preserve-unknown")
        self.assertEqual(review.classify(
            (self.now, "synced", 1, None, False), self.now),
            "preserve-unknown")

    def test_summary_redacts_sources_and_is_not_delete_permission(self):
        rows = [self.row(1), self.row(2, "synced"), self.row(1, pointer=True)]
        r = review._collect(rows, self.now)
        self.assertEqual(r["reviewOldFailedOriginalBatches"], 1)
        self.assertEqual(r["protectedProductOrExampleBatches"], 1)
        self.assertEqual(r["protectedReferenceBatches"], 1)
        self.assertEqual(r["sampledOldBatches"], 3)
        self.assertFalse(r["oldImageDeletionAuthorized"])
        self.assertFalse(r["originalRowsChanged"])
        self.assertIsNone(r["physicalBytesFreed"])
        self.assertNotIn("token", str(r))
        self.assertTrue(review._collect([rows[0]]*review._SAMPLE,
                                        self.now)["olderBatchesMayExist"])
        self.assertEqual(review._collect([rows[0]]*(review._SAMPLE+1),
                                         self.now)["status"], "not-observed")

    def test_read_only_sql_no_image_or_identity_projection(self):
        sql = review._SQL
        self.assertIn("Europe/Zurich", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertNotIn("DELETE ", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("SELECT *", sql.upper())
        self.assertNotIn("SELECT I.PAYLOAD", sql.upper())
        self.assertNotIn("SELECT I.TOKEN_HASH", sql.upper())
        self.assertNotIn("SELECT I.BATCH_ID", sql.upper())
        self.assertNotIn("VACUUM", inspect.getsource(review).upper())


class ReadOnlyProbeTests(unittest.TestCase):
    def test_bounded_query_only_and_no_original_mutation(self):
        now = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)
        class Fake:
            def __init__(self):
                self.statements = []
            def transaction(self):
                return nullcontext()
            def execute(self, sql, params=()):
                self.statements.append((sql, params))
                return self
            def fetchall(self):
                return [(now-timedelta(days=4), "synced", True, None, False)]
        f = Fake()
        with patch.object(review, "_cached", None), \
             patch.object(review, "_cached_at", 0):
            result = review.report(f, now)
        self.assertEqual(result["protectedProductOrExampleBatches"], 1)
        self.assertEqual(len(f.statements), 3)
        self.assertEqual(f.statements[-1][1], (review._SAMPLE,))
        self.assertTrue(all(
            sql.startswith("SET LOCAL") or sql.lstrip().startswith("SELECT")
            for sql, _ in f.statements))
        self.assertFalse(result["oldImageDeletionAuthorized"])

    def test_sql_failure_returns_only_redacted_status(self):
        class Broken:
            def transaction(self):
                raise RuntimeError("private-isin-and-credential")
        with patch.object(review, "_cached", None), \
             patch.object(review, "_cached_at", 0):
            result = review.report(Broken())
        self.assertEqual(result["status"], "not-observed")
        self.assertNotIn("private", str(result))
        self.assertFalse(result["oldImageDeletionAuthorized"])


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "PostgreSQL isolated CI database")
class PostgresAgeReviewTests(unittest.TestCase):
    def test_old_synced_images_stay_and_no_images_are_read_out(self):
        import psycopg
        from psycopg import sql
        schema = "age_review_" + uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(
                sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(
                    sql.Identifier(schema)))
                conn.execute("""CREATE TABLE bob_android_list_images (
                    batch_id text PRIMARY KEY, token_hash text,
                    created_at timestamptz NOT NULL,
                    import_receipt jsonb,parsed_items jsonb,
                    processing_at timestamptz,payload jsonb NOT NULL)""")
                conn.execute("""INSERT INTO bob_android_list_images
                    VALUES ('old-proof','synthetic',now()-interval '4 days',
                    '{"stage":"synced"}'::jsonb,'[]'::jsonb,NULL,
                    '{"images":[{"png":"private-synthetic-png"}]}'::jsonb)""")
                conn.execute("""INSERT INTO bob_android_list_images
                    VALUES ('old-failed','synthetic',now()-interval '3 days',
                    '{"stage":"read-failed"}'::jsonb,NULL,NULL,
                    '{"images":[{"png":"different-private-synthetic-png"}]}'::jsonb)""")
                with patch.object(review, "_cached", None), \
                     patch.object(review, "_cached_at", 0):
                    result = review.report(conn)
                self.assertEqual(result["sampledOldBatches"], 2)
                self.assertEqual(result["protectedProductOrExampleBatches"], 1)
                self.assertEqual(result["reviewOldFailedOriginalBatches"], 1)
                self.assertFalse(result["oldImageDeletionAuthorized"])
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM bob_android_list_images"
                ).fetchone()[0], 2)
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
