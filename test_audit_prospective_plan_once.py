"""Operator-only audit planner probe: no SQL execution and no raw leakage."""
import copy
import unittest
from unittest.mock import Mock, patch

import audit_prospective_plan_once as probe


class Conn:
    def __init__(self, root):
        self.root = root
        self.commands = []
    def transaction(self):
        class Context:
            def __enter__(_): return None
            def __exit__(_, exc_type, exc, tb): return False
        return Context()
    def execute(self, sql, params=()):
        self.commands.append((sql, params))
        return Mock(fetchone=lambda: ([copy.deepcopy(self.root)],))


class AuditPlanProbeTests(unittest.TestCase):
    def plan(self):
        return {
            "Plan":{
                "Node Type":"Sort","Total Cost":244.125,
                "Plans":[{"Node Type":"Nested Loop","Total Cost":123.4,
                    "Plans":[{"Node Type":"Index Only Scan",
                        "Index Name":"PRIVATE_INDEX_NAME", "Relation Name":"PRIVATE",
                        "Total Cost":35.5},
                    {"Node Type":"Seq Scan","Total Cost":99.7,
                     "Filter":"SECRET_INCLUDING_ACCOUNT"}]}]},
            "Planning Time":5.5,
            "Triggers":[{"private":"SECRET"}],
        }

    def test_exact_research_query_uses_planner_without_analyze_or_rows(self):
        db = Conn(self.plan())
        result=probe.inspect(db)
        self.assertEqual(result["status"],"bounded-planner-estimate")
        self.assertEqual(result["indexPlanNodes"],1)
        self.assertEqual(result["sequentialPlanNodes"],1)
        self.assertEqual(result["estimatedRootCost"],244.125)
        self.assertIs(result["sqlExecuted"],False)
        self.assertIs(result["explainAnalyzeUsed"],False)
        self.assertIs(result["causeVerified"],False)
        self.assertEqual(len(db.commands),4)
        query,params=db.commands[-1]
        self.assertTrue(query.startswith("EXPLAIN (FORMAT JSON, ANALYZE FALSE"))
        self.assertIn("CROSS JOIN LATERAL",query)
        self.assertEqual(len(params),1)
        self.assertNotIn("SECRET",str(result))
        self.assertNotIn("PRIVATE",str(result))
        self.assertNotIn("INDEX_NAME",str(result))
        self.assertNotIn("SELECT a.id",str(result))

    def test_malformed_or_private_plan_data_stays_unavailable(self):
        for value in (None, {}, [], [1], [{"Plan":{}}],
                      [{"Plan":{"Node Type":42,"Total Cost":4}}],
                      [{"Plan":{"Node Type":"Seq Scan","Total Cost":float("nan")}}],
                      [{"Plan":{"Node Type":"Seq Scan","Total Cost":1,"Plans":{}}}]):
            with self.subTest(plan=value),self.assertRaises((ValueError,TypeError)):
                probe.summarize(value)

    def test_default_no_network_or_db_and_contract_rejection(self):
        with patch.dict("os.environ",{},clear=True),patch(
            "psycopg.connect") as connect:
            with self.assertRaises(PermissionError):
                probe.run()
            connect.assert_not_called()
        db=Conn(self.plan())
        with patch.object(probe.decision_audit,"_prospective_query",
                          return_value=("DROP TABLE private",())):
            with self.assertRaisesRegex(ValueError,"contract"):
                probe.inspect(db)
        self.assertEqual(db.commands,[])


if __name__=="__main__":
    unittest.main()
