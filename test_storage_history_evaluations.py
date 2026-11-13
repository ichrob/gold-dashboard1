"""History evaluation pages are resumable and never authorize source deletion."""
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import storage_history_evaluations as hist


class EvaluationUnitTests(unittest.TestCase):
    def test_source_fingerprint_is_bounded_and_private(self):
        now=datetime(2026,10,29,12,tzinfo=timezone.utc)
        page=hist.summarize("decisions", [
            ("secret-1",now,"LONG","true"),
            ("secret-2",now+timedelta(seconds=1),"WAIT","false"),
            ("secret-3",now+timedelta(seconds=2),"unsupported","bad")])
        self.assertEqual(page["rows"],3)
        self.assertEqual(page["categories"],{"LONG":1,"WAIT":1,"unclassified":1})
        self.assertEqual(page["outcomes"],{"false":1,"true":1,"unclassified":1})
        self.assertEqual(len(page["digest"]),64)
        self.assertNotIn("secret-",json.dumps(page))
        self.assertNotIn("unsupported",json.dumps(page))
        self.assertNotIn("bad",json.dumps(page))

    def test_duplicate_unordered_and_unbounded_records_rejected(self):
        now=datetime(2026,10,29,12,tzinfo=timezone.utc)
        row=("x",now,"input","ok")
        with self.assertRaises(ValueError):
            hist.summarize("diagnoses",[row,row])
        with self.assertRaises(ValueError):
            hist.summarize("diagnoses",[("z",now,"input","ok"),row])
        with self.assertRaises(ValueError):
            hist.summarize("unknown",[])
        with self.assertRaises(ValueError):
            hist.summarize("diagnoses",[row]*(hist.PAGE_ROWS+1))

    def test_query_uses_indexable_cursor_and_no_source_mutation(self):
        for area,sql in hist._SOURCES.items():
            with self.subTest(area=area):
                self.assertIn("WHERE (recorded_at,id)>",sql)
                self.assertIn("ORDER BY recorded_at,id LIMIT %s",sql)
                self.assertNotIn("DELETE ",sql.upper())
                self.assertNotIn("UPDATE ",sql.upper())
                self.assertNotIn("SELECT *",sql.upper())

    def test_bounded_fake_capture_stores_only_fingerprint(self):
        from contextlib import nullcontext
        now=datetime(2026,11,4,12,tzinfo=timezone.utc)
        old=now-timedelta(days=4)
        class Fake:
            def __init__(self):
                self.sql=[]
                self.res=None
                self.area=None
            def transaction(self):
                return nullcontext()
            def execute(self,sql,params=()):
                self.sql.append((sql,params))
                if sql.startswith("SELECT pg_try"):
                    self.res=(True,)
                elif "FROM bob_history_eval_cursor WHERE" in sql:
                    self.res=None
                elif sql.startswith("SELECT id,recorded_at"):
                    self.area="diagnoses" if "bob_diagnostic_history" in sql else "decisions"
                    self.res=None
                return self
            def fetchone(self):
                return self.res
            def fetchall(self):
                return [("private-"+self.area,old,"input" if self.area=="diagnoses"
                         else "LONG","ok" if self.area=="diagnoses" else "true")]
        fake=Fake()
        result=hist.capture(fake,now)
        self.assertEqual(result["areas"],{"diagnoses":"page-recorded","decisions":"page-recorded"})
        self.assertFalse(result["deletionAuthorized"])
        self.assertNotIn("private-",str(result))
        writes=[(s,p) for s,p in fake.sql if s.lstrip().startswith("INSERT")]
        self.assertEqual(len(writes),4)
        self.assertFalse(any("DELETE FROM" in s.upper() for s,_ in fake.sql))
        for sql,params in writes:
            if "bob_history_eval_segments" in sql:
                self.assertNotIn("private-",str(params))
                self.assertEqual(params[4],1)

    def test_status_and_error_are_not_delete_permission(self):
        class Fake:
            def transaction(self):
                raise ValueError("private credentials")
        result=hist.report(Fake())
        self.assertEqual(result["status"],"not-observed")
        self.assertFalse(result["deletionAuthorized"])
        self.assertNotIn("private",str(result))


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "Postgres integration requires isolated CI database")
class EvaluationPostgresTests(unittest.TestCase):
    def test_resume_without_rewriting_originals(self):
        import psycopg
        from psycopg import sql
        schema="hist_eval_"+uuid.uuid4().hex
        now=datetime(2026,11,4,12,tzinfo=timezone.utc)
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                conn.execute("""CREATE TABLE bob_diagnostic_history(
                    id text primary key,recorded_at timestamptz not null,
                    stage text,payload jsonb)""")
                conn.execute("""CREATE TABLE bob_decision_audit(
                    id text primary key,recorded_at timestamptz not null,
                    payload jsonb)""")
                conn.execute("CREATE INDEX on bob_diagnostic_history(recorded_at)")
                conn.execute("CREATE INDEX on bob_decision_audit(recorded_at)")
                hist.init(conn)
                conn.execute("""INSERT INTO bob_diagnostic_history VALUES
                    ('d1','2026-10-30 10:00+00','input','{"outcome":"ok"}'),
                    ('d2','2026-10-30 10:01+00','analysis','{"outcome":"failed"}'),
                    ('new','2026-11-04 10:00+00','input','{"outcome":"ok"}')""")
                conn.execute("""INSERT INTO bob_decision_audit VALUES
                    ('a1','2026-10-30 10:00+00','{"direction":"LONG","marketEvaluable":true}'),
                    ('a2','2026-10-30 10:01+00','{"direction":"WAIT","marketEvaluable":false}')""")
                before=(
                    conn.execute("SELECT count(*) FROM bob_diagnostic_history").fetchone()[0],
                    conn.execute("SELECT count(*) FROM bob_decision_audit").fetchone()[0])
                one=hist.capture(conn,now)
                self.assertEqual(one["areas"],{
                    "diagnoses":"page-recorded","decisions":"page-recorded"})
                second=hist.capture(conn,now)
                self.assertEqual(second["areas"],{
                    "diagnoses":"caught-up-as-observed",
                    "decisions":"caught-up-as-observed"})
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM bob_history_eval_segments").fetchone()[0],2)
                self.assertEqual(conn.execute(
                    "SELECT sum(rows_count) FROM bob_history_eval_segments").fetchone()[0],4)
                self.assertEqual((
                    conn.execute("SELECT count(*) FROM bob_diagnostic_history").fetchone()[0],
                    conn.execute("SELECT count(*) FROM bob_decision_audit").fetchone()[0]),before)
                report=hist.report(conn)
                self.assertEqual(report["areas"]["diagnoses"]["processedRows"],2)
                self.assertEqual(report["areas"]["decisions"]["processedRows"],2)
                self.assertFalse(report["deletionAuthorized"])
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__=="__main__":
    unittest.main()
