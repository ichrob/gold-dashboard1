"""Regression for the production /simulation-status net-evidence handoff.

No database network, writes, broker orders or extra evidence queries.
"""
import contextlib
import json
import unittest
from unittest.mock import Mock, patch

import bob_diagnostics as diag
import paper_portfolios
from test_paper_net_evidence import closed_case


class FakeIndexedDay:
    def __init__(self, cases):
        self.cases = cases
        self.selected = []
    def transaction(self):
        return contextlib.nullcontext()
    def execute(self, sql, params=None):
        self.selected.append(sql)
        if sql.startswith("SET LOCAL"):
            return Mock()
        if "SELECT payload FROM" in sql and "WHERE day=%s" in sql:
            return Mock(fetchall=lambda: [(c,) for c in self.cases])
        raise RuntimeError("This synthetic DB has no other report tables")


class DayEvidenceTests(unittest.TestCase):
    def run_day(self, cases):
        db = FakeIndexedDay(cases)
        with patch.object(diag, "push_snapshot", return_value={
                "status":"observed", "accounts":[{"profile":"trend800nov"}]}), \
             patch.object(diag, "analysis_snapshot", return_value={"status":"unavailable"}):
            out = diag.simulation_status(db, None, None, paper_portfolios)
        return db, out["accounts"][0]

    def test_sample_is_computed_from_same_selected_day_cases(self):
        db, account = self.run_day([closed_case()])
        # One indexed daily SELECT for the one account, zero new net-audit SQL.
        # Count only the existing indexed current-day case read. Other
        # independent study readers may also try SELECT and fail closed.
        selects = [s for s in db.selected
                   if s.startswith("SELECT payload FROM") and "WHERE day=%s" in s]
        self.assertEqual(len(selects),1)
        self.assertEqual(account["recentCases"]["status"],"observed")
        net = account["netEvidenceSample"]
        self.assertEqual(net["status"],"observed")
        self.assertEqual(net["modelEvidenceEligible"],1)
        self.assertGreater(net["sampleModelNetEur"],0)
        self.assertFalse(net["brokerNetVerified"])
        self.assertFalse(net["fullHistoryRead"])
        self.assertNotIn("private-test-instrument",json.dumps(net))

    def test_empty_daily_sample_does_not_certify_old_account_profit(self):
        db, account = self.run_day([])
        self.assertEqual(account["recentCases"]["items"],[])
        net=account["netEvidenceSample"]
        self.assertEqual(net["status"],"not-yet-observed")
        self.assertEqual(net["sampled"],0)
        self.assertIsNone(net["sampleModelNetEur"])
        self.assertFalse(net["brokerNetVerified"])

    def test_missing_daily_query_fails_closed_without_net_claims(self):
        class Broken(FakeIndexedDay):
            def execute(self, sql, params=None):
                if "WHERE day=%s" in sql:
                    raise RuntimeError("Synthetic outage: do not show private DB exception")
                return super().execute(sql,params)
        db=Broken([])
        with patch.object(diag, "push_snapshot", return_value={
                "status":"observed", "accounts":[{"profile":"trend800nov"}]}), \
             patch.object(diag, "analysis_snapshot", return_value={"status":"unavailable"}):
            out=diag.simulation_status(db,None,None,paper_portfolios)
        net=out["accounts"][0]["netEvidenceSample"]
        self.assertEqual(net["status"],"unavailable")
        self.assertFalse(net["brokerNetVerified"])
        self.assertNotIn("Synthetic outage",json.dumps(net))


if __name__=="__main__":
    unittest.main()
