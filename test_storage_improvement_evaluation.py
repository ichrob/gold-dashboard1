"""Regression tests for source-preserving, capped improvement evaluations."""
import json
import os
import unittest
import uuid

import storage_improvement_evaluation as improvements


class UnitTests(unittest.TestCase):
    def test_labels_digest_and_private_campaign(self):
        rows=[("secret-campaign",1,True,"verified"),
              ("secret-campaign",2,False,"failed"),
              ("secret-campaign",3,True,"not-an-approval")]
        result=improvements.summarize(rows)
        self.assertEqual(result["records"],3)
        self.assertEqual(result["counts"],{
            "status:verified":1,"status:failed":1,"status:unclassified":1,
            "valid-input":2,"invalid-input":1})
        self.assertEqual(len(result["fingerprint"]),64)
        self.assertNotIn("secret",json.dumps(result))
        self.assertNotIn("not-an-approval",json.dumps(result))

    def test_cursor_source_is_primary_key_and_never_mutates_original(self):
        self.assertIn("WHERE (campaign,slot)>",improvements._SQL)
        self.assertIn("ORDER BY campaign,slot LIMIT %s",improvements._SQL)
        for forbidden in ("DELETE", "UPDATE", "SELECT *"):
            self.assertNotIn(forbidden,improvements._SQL.upper())

    def test_bounded_and_out_of_order_fail_closed(self):
        cases=[
            [("a",1,True,"verified")]*2,
            [("a",2,True,"verified"),("a",1,True,"failed")],
            [("a",i,True,"pending") for i in range(improvements.PAGE_ROWS+1)],
            [("a",False,True,"verified")],
            [("a","1",True,"verified")],
            [("a",1,True,"verified","unexpected")],
        ]
        for rows in cases:
            with self.subTest(rows=str(rows)[:20]),self.assertRaises(ValueError):
                improvements.summarize(rows)
        self.assertEqual(improvements.summarize([])["records"],0)

    def test_capture_saves_only_aggregate_and_cursor(self):
        from contextlib import nullcontext
        class Fake:
            def __init__(self):
                self.statements=[]
                self.value=None
            def transaction(self):
                return nullcontext()
            def execute(self,sql,params=()):
                self.statements.append((sql,params))
                self.value=(True,) if "pg_try_advisory" in sql else None
                return self
            def fetchone(self):
                return self.value
            def fetchall(self):
                return [("private-campaign",17,False,"rejected")]
        fake=Fake()
        result=improvements.capture(fake)
        self.assertEqual(result["status"],"page-recorded")
        self.assertEqual(result["processed"],1)
        self.assertFalse(result["deletionAuthorized"])
        self.assertNotIn("private-campaign",str(result))
        writes=[(s,p) for s,p in fake.statements if s.strip().startswith("INSERT")]
        self.assertEqual(len(writes),2)
        self.assertNotIn("private-campaign",str(writes[0]))
        self.assertIn("private-campaign",str(writes[1]))  # cursor only
        self.assertFalse(any("DELETE FROM" in s.upper() for s,_ in fake.statements))


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "isolated PostgreSQL integration only")
class PostgresTests(unittest.TestCase):
    def test_resume_and_provisional_status_without_source_rewrite(self):
        import psycopg
        from psycopg import sql
        name="improvement_eval_"+uuid.uuid4().hex
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(name)))
                conn.execute("""CREATE TABLE bob_improvement_observations (
                    campaign TEXT NOT NULL,slot BIGINT NOT NULL,valid BOOLEAN NOT NULL,
                    payload JSONB NOT NULL,
                    PRIMARY KEY(campaign,slot))""")
                improvements.init(conn)
                conn.execute("""INSERT INTO bob_improvement_observations VALUES
                    ('private-a',1,true,'{"status":"testing"}'),
                    ('private-a',2,false,'{"status":"failed"}'),
                    ('private-b',1,true,'{"_bobColdObservationV1":"private-hash"}')""")
                first=improvements.capture(conn)
                self.assertEqual(first["status"],"page-recorded")
                self.assertEqual(first["processed"],3)
                second=improvements.capture(conn)
                self.assertEqual(second["status"],"caught-up-as-observed")
                row=conn.execute("""SELECT records,counts FROM
                    bob_improvement_eval_segments""").fetchone()
                self.assertEqual(row,(3,{"status:testing":1,"status:failed":1,
                             "status:archived-original-not-inline":1,
                             "valid-input":2,"invalid-input":1}))
                self.assertEqual(conn.execute("""SELECT count(*) FROM
                    bob_improvement_observations""").fetchone()[0],3)
                state=improvements.report(conn)
                self.assertEqual(state["processedRecords"],3)
                self.assertFalse(state["improvementVerified"])
                self.assertFalse(state["deletionAuthorized"])
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


if __name__=="__main__":
    unittest.main()
