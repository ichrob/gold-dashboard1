"""Pure bounded scanner safety tests; never invoke Render or original archives."""
from datetime import datetime, timedelta, timezone
import unittest
import cold_analysis_candidate_scan as scanner
import cold_metrics as codec


class StubConnection:
    """Small fake matching the two immutable, read-only query shapes."""
    def __init__(self, n, size):
        start = datetime(2026, 11, 5, tzinfo=timezone.utc)
        self.records = [
            ("id-" + str(i).zfill(4), "analysis", 100.0, None,
             {"payload": "x" * size}, start + timedelta(seconds=i))
            for i in range(n)
        ]
        self.returned = None
        self.statements = []
    def execute(self, sql, params):
        self.statements.append(sql)
        if sql.startswith("WITH page AS MATERIALIZED"):
            if "AND (recorded_at,id)>" in sql:
                after = (params[0], params[1])
                available = [r for r in self.records if (r[5], r[0]) > after]
            else:
                available = self.records
            self.returned = [(r[0], r[5], True) for r in available[:scanner.PAGE_ROWS]]
        elif "WHERE id=ANY" in sql:
            ids = set(params[0])
            self.returned = [r for r in self.records if r[0] in ids]
        else:
            raise AssertionError("Unexpected SQL, never permit mutation")
        return self
    def fetchall(self):
        return self.returned


class BoundedScanUnitTests(unittest.TestCase):
    def test_2mb_boundary_does_not_skip_an_unprocessed_original(self):
        conn = StubConnection(40, 60000)
        first, at, meta1 = scanner.scan(conn)
        self.assertTrue(first)
        self.assertLess(len(first), 40)
        self.assertLess(sum(len(codec.encoded(row)) for row in first), codec.MAX_RAW)
        self.assertEqual(at, (conn.records[len(first)-1][5], conn.records[len(first)-1][0]))
        second, final, meta2 = scanner.scan(conn, at)
        self.assertEqual(len(first) + len(second), 40)
        self.assertIsNone(final)
        self.assertTrue(meta2["atEndOfAvailableWindow"])
        self.assertEqual([r[0] for r in first + second], [r[0] for r in conn.records])
        self.assertTrue(all("WITH page AS MATERIALIZED" in sql or "WHERE id=ANY" in sql
                            for sql in conn.statements))
        self.assertTrue(all("UPDATE" not in sql and "DELETE" not in sql and
                            "INSERT" not in sql for sql in conn.statements))

    def test_cursor_rejects_untrusted_timestamps_without_sql(self):
        conn = StubConnection(1, 1000)
        with self.assertRaises(ValueError):
            scanner.scan(conn, ("2026-11-05", "id-0"))
        self.assertEqual(conn.statements, [])
        with self.assertRaises(ValueError):
            scanner.commit_cursor(("private", 3))
        scanner.commit_cursor(None)

    def test_scanner_progress_is_not_storage_or_restore_authorization(self):
        rows, after, meta = scanner.scan(StubConnection(1, 1500))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(after)
        self.assertTrue(meta["bounded"])
        self.assertFalse(meta["sourceRowsChangedByScan"])


if __name__ == "__main__":
    unittest.main()
