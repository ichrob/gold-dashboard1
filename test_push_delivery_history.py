"""Privacy and classification tests for bounded push delivery evidence."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
import push_delivery_history as history


class PushHistoryTests(unittest.TestCase):
    def test_default_window_and_boundaries(self):
        now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
        result = history.arguments({}, now=now)
        self.assertEqual(result["start"], "2026-10-23T10:00:00+00:00")
        self.assertEqual(result["end"], "2026-10-24T10:00:00+00:00")
        for bad in (
            {"start": "2026-10-23T10:00:00", "end": "2026-10-24T10:00:00Z"},
            {"start": "2026-10-22T10:00:00Z", "end": "2026-10-24T10:00:00Z"},
            {"offset": -1}, {"offset": True}, {"unknown": 1},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                history.arguments(bad, now=now)

    def test_late_persisted_receipt_is_not_browser_display_latency(self):
        at = datetime(2026, 11, 12, 16, 21, 20, tzinfo=timezone.utc)
        measured = history.latency({
            'dataAt': int(at.timestamp()*1000) - 164900,
            'browserShowAt': at.isoformat(),
        })
        self.assertEqual(measured['sourceToReceiptStoredMs'], 164900)
        self.assertEqual(measured['sourceToBrowserReceiptMs'], 164900)
        self.assertIn('not-browser-or-Android-display', measured['scope'])

    def test_test_not_mistaken_for_market_and_no_secrets(self):
        conn = Mock()
        at = datetime(2026, 10, 23, 19, tzinfo=timezone.utc)
        conn.execute.return_value.fetchall.return_value = [
            ("first", at, {
                "outcome": "provider-accepted", "eventKinds": ["early-warning-test"],
                "direction": "LONG", "test": True, "synthetic": True,
                "secret": "NEVER EXPOSE", "endpoint": "private"}),
            ("second", at, {
                "outcome": "provider-accepted", "eventKinds": ["early-warning"],
                "direction": "LONG", "test": False, "synthetic": False,
                "signalBarAt": 123, "dataAt": 456,
                "token": "NEVER EXPOSE"}),
        ]
        report = history.report(conn)
        first, second = report["records"]
        self.assertEqual(first["eventKinds"], ["early-warning-test"])
        self.assertEqual(second["eventKinds"], ["early-warning"])
        self.assertEqual(first["classification"], "synthetic-test")
        self.assertEqual(second["classification"], "not-marked-test")
        self.assertIs(second["marketEventVerified"], False)
        self.assertEqual(first["handsetReceipt"], "not-verified")
        self.assertNotIn("secret", str(report))
        self.assertNotIn("NEVER EXPOSE", str(report))
        self.assertEqual(conn.execute.call_args.args[1][2:], (101, 0))


    def test_receipt_slices_keep_proven_click_and_browser_clock(self):
        from unittest.mock import MagicMock
        rid = 'a' * 32
        stamp = datetime.now(timezone.utc)
        conn = MagicMock()
        attempt = ("event-1", stamp, {"receiptId": rid, "outcome": "provider-accepted"})
        conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[attempt])),
            MagicMock(fetchall=MagicMock(return_value=[
                (rid, 'show-resolved', stamp),
                (rid, 'clicked', stamp)])),
        ]
        result = history.report(conn)
        self.assertEqual(result['receiptLookupStatus'], 'complete')
        self.assertTrue(result['receiptHistoryComplete'])
        self.assertEqual(result['records'][0]['browserShowReceipt'], 'confirmed')
        self.assertEqual(result['records'][0]['handsetReceipt'], 'notification-click-confirmed')
        self.assertEqual(conn.execute.call_count, 2)
        args = conn.execute.call_args.args[1]
        self.assertEqual(args, (1, 0, [rid]))
        self.assertIn("recorded_at >= now() -", conn.execute.call_args.args[0])

    def test_receipt_statement_timeout_returns_attempt_without_false_confirmation(self):
        from unittest.mock import MagicMock
        import psycopg
        rid = 'b' * 32
        conn = MagicMock()
        conn.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[
                ("event-2", datetime.now(timezone.utc),
                 {"receiptId": rid, "outcome": "provider-accepted"})])),
            psycopg.errors.QueryCanceled('statement timeout'),
        ]
        result = history.report(conn)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(result['receiptLookupStatus'], 'timeout-incomplete')
        self.assertFalse(result['receiptHistoryComplete'])
        self.assertEqual(result['records'][0]['browserShowReceipt'], 'not-verified')
        self.assertEqual(result['records'][0]['handsetReceipt'], 'not-verified')
        self.assertEqual(result['records'][0]['marketEventVerified'], False)


import os
from datetime import timedelta
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class ReceiptDatabaseTests(unittest.TestCase):
    def test_seven_day_read_only_receipts_keep_original_timestamps(self):
        import uuid
        import json
        import psycopg
        from psycopg import sql
        schema = 'receipt_bounded_' + uuid.uuid4().hex
        rid = 'a' * 32
        at = datetime.now(timezone.utc)
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute('''CREATE TABLE bob_diagnostic_history (
                    id TEXT PRIMARY KEY, recorded_at TIMESTAMPTZ, stage TEXT,
                    payload JSONB NOT NULL)''')
                conn.execute('CREATE INDEX receipt_test_stage_time ON bob_diagnostic_history(stage,recorded_at DESC)')
                docs = [
                    ('sent', at-timedelta(hours=3), {"outcome":"provider-accepted","receiptId":rid}),
                    ('show', at-timedelta(hours=2), {"outcome":"browser-receipt","receiptId":rid,"receiptState":"show-resolved"}),
                    ('click', at-timedelta(hours=1), {"outcome":"browser-receipt","receiptId":rid,"receiptState":"clicked"}),
                    ('old', at-timedelta(days=8), {"outcome":"browser-receipt","receiptId":rid,"receiptState":"clicked"}),
                ]
                for name,when,payload in docs:
                    conn.execute('INSERT INTO bob_diagnostic_history VALUES (%s,%s,%s,%s::jsonb)',
                                 (name,when,'push-delivery',json.dumps(payload)))
                conn.commit()
                conn.execute('SET TRANSACTION READ ONLY')
                result = history.report(conn)
                self.assertEqual(result['receiptLookupStatus'], 'complete')
                self.assertEqual(result['records'][0]['handsetReceipt'], 'notification-click-confirmed')
                self.assertEqual(result['records'][0]['browserShowReceipt'], 'confirmed')
                self.assertEqual(result['records'][0]['notificationClickedAt'],
                                 (at-timedelta(hours=1)).isoformat())
                conn.commit()
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()


if __name__ == "__main__":
    unittest.main()
