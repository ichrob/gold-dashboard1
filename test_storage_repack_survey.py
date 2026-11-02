"""One-shot WAL survey: no writes, no secrets, no physical space claims."""
import io
import json
import os
import unittest
from unittest.mock import patch

import storage_repack_survey as survey


class SurveyTests(unittest.TestCase):
    def fixture(self):
        row=(66_838_528,11_157_504,2_736_128,52_912_128,
             16_133,0,12345,16_500,0)
        ext={"pg_repack":{"available":True,"installed":False,"version":"1.5.3"},
             "pgstattuple":{"available":True,"installed":False,"version":"1.5"}}
        return row,ext

    def test_counter_delta_not_a_bloat_or_disk_savings_claim(self):
        row,ext=self.fixture()
        report=survey.evaluate((row,ext,(1000,"fixed-reset"),(2,33_554_432)),
                      (row,ext,(1700,"fixed-reset"),(3,50_331_648)),15,
                      687_841_300,True)
        self.assertEqual(report["walGeneratedBytesInWindow"],700)
        self.assertEqual(report["walCounterStatus"],"observed")
        self.assertEqual(report["walDirectoryObservedBytes"],50_331_648)
        self.assertEqual(report["walFileCount"],3)
        self.assertEqual(report["walDirectoryObservationStatus"],"observed")
        self.assertEqual(report["totalRelationBytes"],66_838_528)
        self.assertEqual(report["toastBytes"],52_912_128)
        self.assertFalse(report["pgRepackExtensionInstalled"])
        self.assertTrue(report["pgRepackClientPresent"])
        self.assertIsNone(report["actualTableBloatBytes"])
        self.assertIsNone(report["walFreeHeadroomBytes"])
        self.assertFalse(report["maintenanceAuthorized"])
        self.assertFalse(report["readyToRepack"])
        self.assertFalse(report["deletionAuthorized"])
        self.assertIsNone(report["diskBytesFreed"])
        output=json.dumps(report)
        self.assertNotIn("DATABASE_URL",output)

    def test_missing_reset_or_reversed_counter_not_observed(self):
        row,ext=self.fixture()
        for first,second in (
            ((200,"A"),(100,"A")),
            ((100,"A"),(180,"B")),
            (None,(180,"A")),
            ((100,"A"),None)
        ):
            with self.subTest(first=first,second=second):
                result=survey.evaluate((row,ext,first,None),(row,ext,second,None),
                                       15,None,False)
                self.assertIsNone(result["walGeneratedBytesInWindow"])
                self.assertEqual(result["walCounterStatus"],"not-observed")
                self.assertFalse(result["readyToRepack"])

    def test_invalid_window_never_claims_approval(self):
        row,ext=self.fixture()
        with self.assertRaises(ValueError):
            survey.evaluate((row,ext,None,None),(row,ext,None,None),1,1000,False)

    def test_disabled_flag_no_db_or_background_work(self):
        with patch.dict(os.environ,{"BOB_REPACK_SURVEY_ONCE":""}), \
             patch.object(survey,"inspect_once",
                          side_effect=AssertionError("must not probe")):
            self.assertIsNone(survey.start_if_enabled())

    def test_snapshot_is_read_only_and_bounded(self):
        row,extensions=self.fixture()
        class Cursor:
            def __init__(self,v):self.value=v
            def fetchone(self):return self.value
            def fetchall(self):return self.value
        class Conn:
            def __init__(self):self.sql=[]
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,q):
                self.sql.append(q)
                if q==survey._RELATION_SQL:
                    return Cursor(row)
                if q==survey._EXT_SQL:
                    return Cursor([("pg_repack","1.5.3",None),
                                   ("pgstattuple","1.5",None)])
                if q==survey._WAL_SQL:
                    return Cursor((100,"2026-11-02T06:00Z"))
                if q==survey._WAL_DIR_SQL:
                    return Cursor((3,50_331_648))
                raise AssertionError("Unexpected query")
        conn=Conn()
        with patch.object(survey,"_connect",return_value=conn):
            a,b,c,d=survey._snapshot()
        self.assertEqual(a,row)
        self.assertTrue(b["pg_repack"]["available"])
        self.assertFalse(b["pg_repack"]["installed"])
        self.assertEqual(c[0],100)
        self.assertEqual(d,(3,50_331_648))
        self.assertEqual(len(conn.sql),4)
        self.assertTrue(all(x.lstrip().startswith("SELECT") for x in conn.sql))
        sql=" ".join(conn.sql).lower()
        for forbidden in ("delete from","update bob_","vacuum ","pg_repack --",
                          "create extension","drop table","pgstattuple_approx("):
            self.assertNotIn(forbidden,sql)

    def test_error_public_status_never_contains_private_details(self):
        class Runner:
            def __call__(self):raise ValueError("secret db password")
        with patch.object(survey,"inspect_once",side_effect=Runner()), \
             patch.dict(os.environ,{"BOB_REPACK_SURVEY_ONCE":"1"}), \
             patch("threading.Thread") as thread:
            survey.start_if_enabled()
            callback=thread.call_args.kwargs["target"]
            import contextlib
            output=io.StringIO()
            with contextlib.redirect_stdout(output): callback()
        self.assertNotIn("password",output.getvalue())
        self.assertIn("survey-unavailable",output.getvalue())
        self.assertIn('"readyToRepack":false',output.getvalue())


if __name__=="__main__":
    unittest.main()
