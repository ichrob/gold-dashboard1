"""Source-preserving daily quality summaries of stored metric checks."""
import json
import os
import unittest
import uuid
from datetime import datetime, timezone, timedelta

import storage_quality_evaluation as quality


class QualityFoldTests(unittest.TestCase):
    def setUp(self):
        self.ms=int(datetime(2026,11,3,12,tzinfo=timezone.utc).timestamp()*1000)
        self.limit=self.ms+3600000

    def record(self,scope,at,state,bar=1):
        return ("metric-quality-v1",scope,bar,at,state)

    def test_aggregate_categories_not_real_metric_pass(self):
        rows=[self.record("dmi:15m",self.ms,"matched",1),
              self.record("dmi:15m",self.ms+1,"mismatch",2),
              self.record("product:private-isin",self.ms+2,
                          "archived-original-not-inline",3),
              self.record("trade:private-case",self.ms+3,
                          "individual-metrics-no-overall-status",4)]
        groups=quality.fold(rows,self.limit)
        self.assertEqual(groups[("2026-11-03","dmi")]["counts"],
                         {"matched":1,"mismatch":1})
        self.assertEqual(groups[("2026-11-03","product")]["counts"],
                         {"archived-original-not-inline":1})
        self.assertEqual(groups[("2026-11-03","trade")]["counts"],
                         {"individual-metrics-no-overall-status":1})
        self.assertNotIn("private",str(groups))
        self.assertEqual(len(groups[("2026-11-03","dmi")]["digests"][0]),32)

    def test_unknown_status_is_unclassified_and_errors_stop_capture(self):
        day,family,status,_ = quality.validate(
            self.record("display:1m",self.ms,"issuer says perfect"),self.limit)
        self.assertEqual((day,family,status),("2026-11-03","display","unclassified"))
        with self.assertRaises(ValueError):
            quality.fold([self.record("dmi:15m",self.ms+1,"observed"),
                          self.record("dmi:15m",self.ms,"observed")],self.limit)
        with self.assertRaises(ValueError):
            quality.fold([self.record("dmi:15m",self.ms,"observed")] *
                         (quality._PAGE+1),self.limit)
        with self.assertRaises(ValueError):
            quality.validate(self.record("dmi:15m",self.limit+1,"matched"),
                             self.limit)
        self.assertEqual(quality.fold([],self.limit),{})

    def test_source_query_reads_status_only_with_exact_cursor(self):
        self.assertIn("ORDER BY checked_at,version,scope,bar_at LIMIT %s",quality._SQL)
        self.assertIn("payload ? '_bobColdMetricV2'",quality._SQL)
        self.assertNotIn("SELECT *",quality._SQL.upper())
        self.assertNotIn("DELETE FROM",quality._SQL.upper())
        self.assertNotIn("UPDATE",quality._SQL.upper())


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "PostgreSQL CI integration requires isolated database")
class QualityPostgresTests(unittest.TestCase):
    def test_daily_rollup_resume_cold_pointer_and_no_source_mutation(self):
        import psycopg
        from psycopg import sql
        schema="quality_eval_"+uuid.uuid4().hex
        checked=int(datetime(2026,10,30,12,tzinfo=timezone.utc).timestamp()*1000)
        with psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                             autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
                conn.execute("""CREATE TABLE bob_metric_checks (
                    version TEXT,scope TEXT,bar_at BIGINT,checked_at BIGINT,
                    payload JSONB NOT NULL, PRIMARY KEY(version,scope,bar_at))""")
                conn.execute("CREATE INDEX ON bob_metric_checks(checked_at)")
                quality.init(conn)
                conn.execute("""INSERT INTO bob_metric_checks VALUES
                    ('v1','dmi:15m',1,%s,'{"status":"matched"}'),
                    ('v1','dmi:5m',2,%s,'{"status":"mismatch"}'),
                    ('v1','product:private',3,%s,
                     '{"_bobColdMetricV2":["secret",0]}'),
                    ('v1','trade:private',4,%s,
                     '{"metrics":{"pnl":{"status":"matched"}}}'),
                    ('v1','display:1m',5,%s,'{"status":"matched"}')""",
                    (checked,checked+1,checked+2,checked+3,
                     int(datetime(2026,11,4,13,tzinfo=timezone.utc).timestamp()*1000)))
                now=datetime(2026,11,4,13,tzinfo=timezone.utc)
                first=quality.capture(conn,now)
                self.assertEqual(first["status"],"page-recorded")
                self.assertEqual(first["processed"],4)
                self.assertEqual(quality.capture(conn,now)["status"],
                                 "caught-up-as-observed")
                sums=conn.execute("""SELECT family,records,counts
                    FROM bob_quality_eval_daily ORDER BY family""").fetchall()
                self.assertEqual(sums,[
                    ("dmi",2,{"matched":1,"mismatch":1}),
                    ("product",1,{"archived-original-not-inline":1}),
                    ("trade",1,{"individual-metrics-no-overall-status":1})])
                self.assertEqual(conn.execute(
                    "SELECT count(*) FROM bob_metric_checks").fetchone()[0],5)
                progress=quality.report(conn)
                self.assertEqual(progress["processedRecords"],4)
                self.assertFalse(progress["metricPassVerified"])
                self.assertFalse(progress["deletionAuthorized"])
            finally:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__=="__main__":
    unittest.main()
