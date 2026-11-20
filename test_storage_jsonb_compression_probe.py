"""No live PostgreSQL is contacted by these safety and equality tests."""
import copy
import json
import unittest

import storage_jsonb_compression_probe as p


class FakeConn:
    def __init__(self, name="bob_archive_restore_test"):
        self.name = name
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)
        if sql == "SELECT current_database()":
            return self
        raise AssertionError("Only database identity read permitted")

    def fetchone(self):
        return (self.name,)


class CompressionProbeTests(unittest.TestCase):
    SOURCE = "postgresql://x:y@production.local/bob_push_db"
    RESTORE = "postgresql://x:y@restore.local/bob_archive_restore_test"

    def test_synthetic_rows_are_bounded_and_distinct(self):
        rows = p.fixtures()
        before = copy.deepcopy(rows)
        encoded = p.validate_fixtures(rows)
        self.assertEqual(len(rows), 96)
        self.assertEqual(rows, before)
        self.assertEqual(len(encoded), 96)
        self.assertTrue(all("SYNTHETIC" not in x for x in encoded[:48]))
        self.assertEqual(rows[0]["sourceAt"], 1_800_000_000)
        self.assertEqual(rows[95]["sourceAt"], 1_800_000_047)

    def test_reader_roundtrip_preserves_identity_and_original_clocks(self):
        rows = p.fixtures()
        back = [(i, json.dumps(row)) for i, row in enumerate(rows)]
        self.assertTrue(p.confirm_exact_reader(rows, back))
        altered = list(back)
        altered[1] = (1, json.dumps({**rows[1], "sourceAt": 0}))
        with self.assertRaises(ValueError):
            p.confirm_exact_reader(rows, altered)
        altered = list(back)
        altered[1] = (0, altered[1][1])
        with self.assertRaises(ValueError):
            p.confirm_exact_reader(rows, altered)
        with self.assertRaises(ValueError):
            p.confirm_exact_reader(rows, back[:-1])

    def test_invalid_input_is_rejected_not_truncated(self):
        with self.assertRaises(ValueError):
            p.validate_fixtures([])
        with self.assertRaises(ValueError):
            p.validate_fixtures(p.fixtures() + [{}])
        with self.assertRaises(ValueError):
            p.validate_fixtures([{"kind": "live-product", "payload": {}}])
        with self.assertRaises(ValueError):
            p.validate_fixtures([{"kind": "input-synthetic", "nan": float("nan")}])
        with self.assertRaises(ValueError):
            p.validate_fixtures([{"kind": "decision-synthetic", "blob": "z" * 2_000_001}])

    def test_restore_gate_requires_explicit_enablement_and_distinct_host(self):
        valid = FakeConn()
        with self.assertRaises(PermissionError):
            p.require_isolated_restore(valid, self.SOURCE, self.RESTORE, None)
        self.assertEqual(valid.statements, [])
        p.require_isolated_restore(valid, self.SOURCE, self.RESTORE, "1")
        self.assertEqual(valid.statements, ["SELECT current_database()"])
        for source, target in (
            (self.RESTORE, self.RESTORE),
            (self.SOURCE, "postgresql://x:y@production.local/bob_archive_restore_test"),
            (self.SOURCE, "postgresql://x:y@restore.local/bob_push_db"),
        ):
            with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                p.require_isolated_restore(FakeConn(), source, target, "1")
        with self.assertRaises(ValueError):
            p.require_isolated_restore(FakeConn("bob_push_db"), self.SOURCE, self.RESTORE, "1")


if __name__ == "__main__":
    unittest.main()
