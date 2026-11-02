"""Safety and PostgreSQL tests for immutable gross-only paper receipts."""
import copy
import json
import os
import unittest
import uuid
from datetime import datetime, timezone

import storage_case_results as receipts

START = datetime(2026,10,30,12,0,tzinfo=timezone.utc)
END = datetime(2026,10,30,13,0,tzinfo=timezone.utc)


def closed_case():
    return {
        "status": "closed", "modelOnly": True,
        "productReturnKnown": True, "netReturnKnown": False,
        "pendingUnits": 0, "remainingUnits": 0, "remaining": 0,
        "quantity": 2, "bookedUnits": 2, "allocated": 20.0,
        "cashReleased": 22.0, "productGrossPct": 10.0,
        "events": [{"kind":"virtual-sell", "at": 1793365200000,
                    "quote": {"bid": 11., "at": 1793365200000}}],
    }


class QualificationTests(unittest.TestCase):
    def row(self,payload=None):
        return ("private-case", "2026-10-30", START, END,
                closed_case() if payload is None else payload)

    def test_exact_stored_model_gross_and_hash_no_raw_payload(self):
        a = receipts.qualify("balanced", self.row())
        self.assertEqual(a["resultKind"],
                         "model-gross-arithmetic-consistent-v1")
        self.assertEqual(a["grossPct"], "10.0")
        self.assertEqual(len(a["originalSha256"]), 64)
        self.assertNotIn("events", json.dumps(a))
        again = receipts.qualify("balanced", self.row())
        self.assertEqual(a["originalSha256"], again["originalSha256"])
        changed = closed_case()
        changed["events"].append({"kind": "original-different"})
        self.assertNotEqual(a["originalSha256"],
                            receipts.qualify("balanced",self.row(changed))["originalSha256"])

    def test_never_finalize_mismatched_or_unpriced_trade(self):
        for change in (
            {"status": "inconclusive"},
            {"status": "open"},
            {"modelOnly": False},
            {"productReturnKnown": False},
            {"netReturnKnown": True},
            {"pendingUnits": 1},
            {"remainingUnits": 1},
            {"remaining": 0.5},
            {"quantity": 0},
            {"bookedUnits": 1},
            {"allocated": 0},
            {"cashReleased": -1},
            {"productGrossPct": 11},
            {"productGrossPct": float("nan")},
        ):
            c = closed_case(); c.update(change)
            with self.subTest(change=change):
                self.assertIsNone(receipts.qualify("balanced",self.row(c)))
        case = list(self.row())
        case[3] = None
        self.assertIsNone(receipts.qualify("balanced", tuple(case)))
        with self.assertRaises(ValueError):
            receipts.qualify("arbitrary-public-table",self.row())

    def test_receipt_only_arithmetic_not_broker_net_profit(self):
        data=receipts.qualify("early1000oct",self.row())
        self.assertNotIn("netProfitVerified",data)
        self.assertNotIn("executionConfirmed",data)
        self.assertEqual(data["profile"],"early1000oct")


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "CI PostgreSQL integration")
class IntegrationTests(unittest.TestCase):
    def test_isolated_backfill_source_preservation_and_digest_conflicts(self):
        import psycopg
        from psycopg import sql
        import paper_portfolios
        schema="paper_final_"+uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as c:
            c.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                c.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                for profile in ("legacy", *receipts._PROFILES):
                    table=("bob_paper_cases" if profile=="legacy" else
                           paper_portfolios.names(profile)["bob_paper_cases"])
                    c.execute("CREATE TABLE "+table+"(id TEXT PRIMARY KEY, "
                              "day TEXT,started_at TIMESTAMPTZ, "
                              "closed_at TIMESTAMPTZ,payload JSONB)")
                receipts.init(c)
                original=closed_case()
                c.execute("""INSERT INTO bob_paper_balanced_cases
                    VALUES('case1','2026-10-30',%s,%s,%s::jsonb)""",
                          (START,END,json.dumps(original)))
                unpriced=closed_case()
                unpriced["status"]="inconclusive"
                c.execute("""INSERT INTO bob_paper_normal1000oct_cases
                    VALUES('no-fill','2026-10-30',%s,%s,%s::jsonb)""",
                          (START,END,json.dumps(unpriced)))
                first=receipts.capture(c)
                self.assertEqual(first["areas"]["balanced"]["newReceipts"],1)
                self.assertEqual(first["areas"]["normal1000oct"]["newReceipts"],0)
                self.assertEqual(c.execute("SELECT count(*) FROM bob_paper_final_receipts").fetchone()[0],1)
                source=c.execute("SELECT payload FROM bob_paper_balanced_cases").fetchone()[0]
                self.assertEqual(source,original)
                # First sweep restarts after its last page; third run reads
                # it again, but does not update the immutable receipt.
                receipts.capture(c)
                repeated=receipts.capture(c)
                self.assertEqual(repeated["areas"]["balanced"]["identicalReceipts"],1)
                self.assertEqual(repeated["areas"]["balanced"]["newReceipts"],0)
                self.assertEqual(receipts.report(c)["grossOnlyReceiptsByLedger"]["balanced"],1)
                mutated=copy.deepcopy(original)
                mutated["events"].append({"kind":"late-evidence"})
                c.execute("""UPDATE bob_paper_balanced_cases SET payload=%s::jsonb
                    WHERE id='case1'""",(json.dumps(mutated),))
                receipts.capture(c)
                conflict=receipts.capture(c)
                self.assertEqual(conflict["status"],"partial")
                self.assertEqual(conflict["areas"]["balanced"]["status"],"source-mismatch")
                self.assertEqual(conflict["areas"]["balanced"]["conflicts"],1)
                self.assertEqual(c.execute("SELECT payload FROM bob_paper_balanced_cases").fetchone()[0],mutated)
                self.assertEqual(c.execute("SELECT count(*) FROM bob_paper_final_receipts").fetchone()[0],1)
                status=receipts.report(c)
                self.assertFalse(status["netProfitVerified"])
                self.assertFalse(status["fullHistoryVerified"])
                self.assertFalse(status["independentRestoreVerified"])
                self.assertFalse(status["deletionAuthorized"])
                self.assertIsNone(status["physicalBytesFreed"])
            finally:
                c.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
