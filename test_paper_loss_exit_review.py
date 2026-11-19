"""Forward-only loss-review projection from already settled Bob paper reflections."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

import paper_profit_summary as profit
import bob_diagnostics as diag


class PaperLossReviewProjectionTests(unittest.TestCase):
    def reflection(self):
        return {
            "version":"paper-reflection-v1", "reviewed":4, "evaluated":3,
            "unpriced":1, "modelLosses":2, "modelNetEur":-54.2,
            "lastAt":1795093000000,
            "secretToken":"NEVER-LEAK-TOKEN",
            "recent":[
                dict(version="paper-reflection-v1",exitReason="stop",
                     caseId="PRIVATE-ISIN-1", costModel=dict(modelNetEur=-22,grossEur=-15,
                         secret="PRIVATE-QUOTE"),observations=["PRIVATE-INFO"]),
                dict(version="paper-reflection-v1",exitReason="target-exit",
                     costModel=dict(modelNetEur=7.5,grossEur=12)),
                dict(version="paper-reflection-v1",exitReason="time-exit",
                     costModel=dict(modelNetEur=-39.7,grossEur=1.1)),
                dict(version="paper-reflection-v1",exitReason="reversal-exit",
                     costModel=None),
            ]}

    def test_aggregate_existing_exit_reasons_and_cumulative_loss_not_raw_history(self):
        source=self.reflection()
        original=copy.deepcopy(source)
        review=profit.saved_exit_review(source)
        self.assertEqual(source,original)
        self.assertEqual(review["status"],"observed")
        self.assertEqual(review["cumulative"]["reviewed"],4)
        self.assertEqual(review["cumulative"]["modeledEvaluated"],3)
        self.assertEqual(review["cumulative"]["modeledLosses"],2)
        self.assertEqual(review["cumulative"]["unpriced"],1)
        self.assertEqual(review["cumulative"]["modelNetEur"],-54.2)
        self.assertEqual(review["recentSample"]["modeledLosses"],2)
        self.assertEqual(review["recentSample"]["modeledWins"],1)
        self.assertEqual(review["recentSample"]["unpriced"],1)
        self.assertEqual(review["recentSample"]["grossPositiveButNetNonPositive"],1)
        self.assertEqual(review["recentExitReasons"],
            {"stop":1,"target-exit":1,"time-exit":1,"reversal-exit":1})
        self.assertFalse(review["brokerNetVerified"])
        self.assertFalse(review["fullHistoryRead"])
        for private in ("PRIVATE-ISIN","NEVER-LEAK","PRIVATE-QUOTE","PRIVATE-INFO"):
            self.assertNotIn(private,json.dumps(review))

    def test_invalid_or_absent_reflections_not_invented(self):
        self.assertEqual(profit.saved_exit_review(None)["status"],"not-yet-observed")
        bad=self.reflection();bad["evaluated"]=5
        self.assertEqual(profit.saved_exit_review(bad)["status"],"invalid-stored-summary")
        bad=self.reflection();bad["modelNetEur"]=float("nan")
        v=profit.saved_exit_review(bad)
        self.assertEqual(v["status"],"observed")
        self.assertIsNone(v["cumulative"]["modelNetEur"])
        json.dumps(v,allow_nan=False)
        injected={"status":"observed","cumulative":{"reviewed":2,"productId":"PRIVATE"},
                  "recentExitReasons":{"secret":"PRIVATE-ISIN","stop":1},
                  "recentSample":{"modeledLosses":1,"raw":"PRIVATE"}}
        projected=profit.safe_exit_review_projection(injected)
        self.assertNotIn("PRIVATE",json.dumps(projected))
        self.assertFalse(projected["brokerNetVerified"])

    def test_projection_in_private_account_and_profit_view_without_extra_db_reads(self):
        profiles=("ema3000nov","noema5000nov","early1000dec","early5m1000nov")
        source=self.reflection()
        controls={p:{"status":"running","initialCapital":3000 if p=="ema3000nov" else 1000,
                     "equity":3030 if p=="ema3000nov" else 990,
                     "reflection":copy.deepcopy(source),
                     "privateToken":"SECRET-CONNECTION"} for p in profiles}
        class Cursor:
            def __init__(self,value): self.value=value
            def fetchone(self): return self.value
        class Connection:
            def __init__(self):self.queries=[]
            def execute(self,sql):
                self.queries.append(sql)
                if "FROM subscriptions" in sql: return Cursor((0,0))
                for p in profiles:
                    if "FROM mock_paper_"+p+"_control" in sql:
                        return Cursor((controls[p],))
                raise AssertionError("Unexpected SQL")
        class Portfolios:
            POLICIES={p:{} for p in profiles}
            @staticmethod
            def names(p):return {"bob_paper_control":"mock_paper_"+p+"_control"}
        class Health:
            @staticmethod
            def snapshot(_): return {"state":"ok"}
        class Evaluator:
            @staticmethod
            def status():return {"completed":1,"failed":0}
        c=Connection()
        import report_admission, decision_audit
        with (patch.object(report_admission,"status",return_value={}),
              patch.object(decision_audit,"prospective_query_probe",return_value={})):
            live=diag.push_snapshot(c,Evaluator(),Health(),Portfolios())
        self.assertEqual(len(c.queries),5) # 4 control SELECTs and one push aggregate
        out=profit.snapshot(live["accounts"])
        for p in profiles:
            row=next(x for x in out["rows"] if x["profile"]==p)
            self.assertEqual(row["modelExitReview"]["recentSample"]["modeledLosses"],2)
            self.assertEqual(row["modelExitReview"]["cumulative"]["modelNetEur"],-54.2)
            self.assertFalse(row["modelExitReview"]["brokerNetVerified"])
        self.assertNotIn("SECRET-CONNECTION",json.dumps(out))
        self.assertNotIn("PRIVATE-ISIN",json.dumps(out))
        self.assertFalse(out["netProductReturnsVerified"])


if __name__=="__main__":
    unittest.main()
