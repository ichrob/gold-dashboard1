"""Paper rollups preserve original receipts, simulated losses and uncertainty."""
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import storage_paper_evaluation as paper


class PaperEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.at=datetime(2026,10,30,12,tzinfo=timezone.utc)
    def item(self,profile="normal1000oct",key="case1",gross=Decimal("2.4"),
             kind="model-gross-arithmetic-consistent-v1",at=None):
        return (profile,key,"2026-10-30",self.at if at is None else at,
                "a"*64,kind,gross)

    def test_only_valid_model_gross_signs_and_provenance_digest(self):
        rows=[self.item(key="c1",gross=Decimal("-3.5")),
              self.item(key="c2",gross=Decimal("0")),
              self.item(key="c3",gross=Decimal("1.5")),
              self.item(key="c4",gross=Decimal("55"),kind="unverified")]
        groups=paper.fold(rows)
        self.assertEqual(len(groups),1)
        x=groups[("normal1000oct","2026-10-30")]
        self.assertEqual((x["positive"],x["negative"],x["flat"],x["unclassified"]),
                         (1,1,1,1))
        self.assertEqual(len(x["digests"]),4)
        self.assertNotIn("caseId",json.dumps(x))
        self.assertNotIn("grossPct",json.dumps(x))

    def test_invalid_or_out_of_order_never_produce_evaluation(self):
        with self.assertRaises(ValueError):
            paper.fold([self.item(key="c2"),self.item(key="c1")])
        with self.assertRaises(ValueError):
            paper.fold([self.item(profile="UNKNOWN")])
        with self.assertRaises(ValueError):
            paper.fold([self.item()]*(paper._PAGE+1))
        with self.assertRaises(ValueError):
            paper.fold([self.item(at=datetime(2026,10,30))])
        self.assertEqual(paper.fold([]),{})

    def test_bound_limits_and_read_only_sources(self):
        self.assertIn("ORDER BY captured_at,profile,case_id LIMIT %s",paper._QUERY)
        self.assertNotIn("DELETE FROM",paper._QUERY.upper())
        self.assertNotIn("SELECT *",paper._QUERY.upper())
        self.assertNotIn("UPDATE",paper._QUERY.upper())


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "PostgreSQL isolated CI database")
class PaperEvalPostgres(unittest.TestCase):
    def test_page_receipts_and_resume_without_changing_sources(self):
        import psycopg
        from psycopg import sql
        schema="paper_eval_"+uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                conn.execute("""CREATE TABLE bob_paper_final_receipts (
                    profile text NOT NULL,case_id text NOT NULL,
                    day text NOT NULL,started_at timestamptz,
                    closed_at timestamptz,original_sha256 text NOT NULL,
                    result_kind text NOT NULL,gross_pct numeric NOT NULL,
                    captured_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY(profile,case_id))""")
                conn.execute("CREATE INDEX ON bob_paper_final_receipts(captured_at DESC)")
                paper.init(conn)
                conn.execute("""INSERT INTO bob_paper_final_receipts
                    (profile,case_id,day,original_sha256,result_kind,
                     gross_pct,captured_at) VALUES
                    ('normal1000oct','c1','2026-10-30',%s,
                     'model-gross-arithmetic-consistent-v1',3.2,%s),
                    ('normal1000oct','c2','2026-10-30',%s,
                     'model-gross-arithmetic-consistent-v1',-1.5,%s),
                    ('early1000oct','c3','2026-10-30',%s,
                     'model-gross-arithmetic-consistent-v1',0,%s)""",
                    ("a"*64,datetime(2026,10,30,10,tzinfo=timezone.utc),
                     "b"*64,datetime(2026,10,30,11,tzinfo=timezone.utc),
                     "c"*64,datetime(2026,10,30,12,tzinfo=timezone.utc)))
                now=datetime(2026,11,4,12,tzinfo=timezone.utc)
                first=paper.capture(conn,now)
                self.assertEqual(first["status"],"page-recorded")
                self.assertEqual(first["processed"],3)
                second=paper.capture(conn,now)
                self.assertEqual(second["status"],"caught-up-as-observed")
                rows=conn.execute("""SELECT profile,source_receipts,positive,
                    negative,flat,unclassified FROM bob_paper_eval_daily
                    ORDER BY profile""").fetchall()
                self.assertEqual(rows,[
                    ("early1000oct",1,0,0,1,0),
                    ("normal1000oct",2,1,1,0,0)])
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM bob_paper_final_receipts"
                ).fetchone()[0],3)
                report=paper.report(conn)
                self.assertEqual(report["processedReceipts"],3)
                self.assertFalse(report["netProfitVerified"])
                self.assertFalse(report["fullHistoryVerified"])
                self.assertFalse(report["deletionAuthorized"])
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__=="__main__":
    unittest.main()
