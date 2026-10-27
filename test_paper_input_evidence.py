"""Post-commit paper input evidence: only observed clocks, no synthetic outcomes."""
import json
import time
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch
import paper_input_evidence as ev
import diagnostic_history
import bob_diagnostics


class _Tx:
    def __enter__(self): return self
    def __exit__(self, *args): return False


def _case(at=1000000):
    return [{"profile":"conservative",
        "recentCases":{"status":"observed","items":[
            {"status":"inconclusive","events":[
                {"kind":"data-gap","recordedAt":at}]}]}}]


class PaperInputEvidenceTests(unittest.TestCase):
    def test_profile_sanitization_is_allowlist_only(self):
        value = ev.sanitized_profile("conservative",{
            "ready":True,"priceFresh":False,"dataAt":45000,"analysisBarAt":42000,
            "price":4123, "trade":{"isin":"PRIVATE"}, "secret":"never"}, "checked")
        self.assertEqual(value,{"profile":"conservative", "outcome":"checked",
            "ready":True,"priceFresh":False,"dataAt":45000,"barAt":42000})
        self.assertIsNone(ev.sanitized_profile("private-profile",{}, "checked"))
        self.assertIsNone(ev.sanitized_profile("conservative",{"dataAt":float("nan")}, "checked")["dataAt"])

    def test_capture_is_enqueue_only_redacted_and_never_claims_delivery(self):
        original={"spots":{"spot_price_as_of":"2026-10-23T19:00:00Z","xaus":4000}}
        profile={"profile":"early100","ready":False,"priceFresh":False,
                 "dataAt":2000,"barAt":1000,"outcome":"evaluation-error",
                 "cash":10000,"isin":"SECRET"}
        with patch.object(diagnostic_history,"emit") as emit:
            self.assertTrue(ev.capture(original,[profile],3000))
        self.assertEqual(emit.call_count,1)
        name, trace, payload = emit.call_args.args
        self.assertEqual(name, "paper-input")
        self.assertEqual(trace,diagnostic_history.trace(original))
        self.assertEqual(payload["phase"],"post-commit")
        self.assertEqual(payload["profiles"][0]["outcome"],"evaluation-error")
        self.assertNotIn("SECRET",json.dumps(payload))
        self.assertNotIn("cash",json.dumps(payload))
        self.assertFalse(ev.capture(original,[],3000))

    def test_diagnostic_projection_has_no_secrets_and_keeps_statuses(self):
        result=diagnostic_history.validate({
            "id":"a"*32,"traceId":"b"*32,"stage":"paper-input",
            "at":time.time(),"payload":{"phase":"post-commit","checkedAt":2000,
                "profiles":[{"profile":"balanced","outcome":"checked",
                             "ready":False,"priceFresh":False,"dataAt":1500,
                             "barAt":1200,"price":42.0,"token":"SECRET"}],
                "token":"SECRET"}})
        self.assertEqual(result["payload"]["profiles"][0]["dataAt"],1500)
        self.assertNotIn("SECRET",json.dumps(result))
        self.assertNotIn("price",json.dumps(result).replace("priceFresh",""))

    def test_archive_record_not_later_claimed_as_earlier_input(self):
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(Decimal("1001.25"),{
            "profiles":[{"profile":"conservative","outcome":"checked","ready":False,
                         "priceFresh":False,"dataAt":500000,"barAt":450000,
                         "secret":"not-visible"}]})
        result=ev.report(conn,_case(),now_ms=1200000)
        self.assertEqual(result["counts"]["workerInputNearby"],1)
        row=result["items"][0]
        self.assertEqual(row["timeRelation"],"after-event")
        self.assertEqual(row["deltaSeconds"],1.25)
        self.assertFalse(row["profiles"][0]["priceFresh"])
        self.assertEqual(result["counts"]["nearbyProfileInputUnfreshOrError"],1)
        self.assertNotIn("not-visible",json.dumps(result))
        sql=conn.execute.call_args.args[0].upper()
        self.assertTrue(sql.lstrip().startswith("SELECT"))
        self.assertNotIn("INSERT ",sql)
        self.assertNotIn("DELETE ",sql)
        self.assertNotIn("UPDATE ",sql)

    def test_missing_archive_is_unconfirmed_not_broken_or_filled(self):
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=None
        result=ev.report(conn,_case(),now_ms=1200000)
        self.assertEqual(result["counts"]["noWorkerCaptureNearby"],1)
        self.assertEqual(result["items"][0]["state"],"no-worker-input-capture-in-window")
        self.assertIn("proves nothing",result["note"])
        conn.execute.side_effect=TimeoutError("Sensitive data")
        result=ev.report(conn,_case(),now_ms=1200000)
        self.assertEqual(result["status"],"partial")
        self.assertEqual(result["counts"]["queryUnavailable"],1)
        self.assertNotIn("Sensitive data",json.dumps(result))

    def test_multiple_profiles_same_gap_only_one_query(self):
        conn=Mock();conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(1000.,{"profiles":[]})
        rows=_case()+[{"profile":"offensive","recentCases":_case()[0]["recentCases"]}]
        result=ev.report(conn,rows,now_ms=1200000)
        self.assertEqual(result["sampledDistinctClocks"],1)
        self.assertEqual(conn.execute.call_count,1)

    def test_capture_failure_cannot_consume_a_paper_account_evaluation(self):
        from contextlib import nullcontext
        import paper_portfolios
        class FakeConn:
            def transaction(self):
                return nullcontext()
        inputs=[]
        market={"ready": True, "priceFresh": True, "dataAt":1000000,
                "analysisBarAt":900000, "direction":"NEUTRAL"}
        with patch("paper_simulation.run_once") as run, \
             patch.object(ev, "sanitized_profile", side_effect=RuntimeError("AUDIT OFFLINE")):
            outcomes = paper_portfolios.run_all(FakeConn(), {}, market,
                {"choices":[]}, {}, 1000000, {}, active={},
                input_observations=inputs)
        self.assertEqual(outcomes, {profile:"checked" for profile in paper_portfolios.POLICIES})
        self.assertEqual(run.call_count,7)
        self.assertEqual(inputs,[])

    def test_monday_readiness_observes_all_five_without_inferring_trades(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        import paper_portfolios
        clock = datetime(2026,10,26,8,5,tzinfo=ZoneInfo("Europe/Zurich"))
        now_ms = clock.timestamp()*1000
        assert clock.utcoffset().total_seconds()==3600  # DST ended Sunday
        captured = now_ms-35000
        conn = Mock()
        conn.transaction.return_value = _Tx()
        profiles = [{"profile":name,"outcome":"checked","ready":True,
                     "priceFresh":True,"dataAt":now_ms-40000,
                     "barAt":now_ms-300000, "price":42,
                     "isin":"PRIVATE"} for name in paper_portfolios.POLICIES]
        conn.execute.return_value.fetchone.return_value = (captured/1000,{"profiles":profiles})
        result = ev.latest(conn,now_ms=now_ms,session_mode="trading")
        self.assertEqual(result["state"],"recent-all-profile-capture")
        self.assertEqual(result["profilesObserved"],7)
        self.assertEqual(result["profilesChecked"],7)
        self.assertEqual(result["profilesFreshReady"],7)
        self.assertEqual(result["ageSeconds"],35)
        self.assertEqual(result["profiles"][0]["sourceAgeAtCaptureSeconds"],5)
        self.assertNotIn("PRIVATE",json.dumps(result))
        sql = conn.execute.call_args.args[0].upper()
        self.assertTrue(sql.lstrip().startswith("SELECT"))
        self.assertIn("PAPER-INPUT",sql)
        self.assertNotIn("INSERT ",sql)
        self.assertNotIn("UPDATE ",sql)
        self.assertNotIn("DELETE ",sql)
        self.assertIn("do not prove trade entries",result["note"])

    def test_weekend_without_capture_is_pause_not_system_failure(self):
        conn = Mock()
        conn.transaction.return_value = _Tx()
        conn.execute.return_value.fetchone.return_value = None
        weekend = ev.latest(conn,now_ms=1000000,session_mode="weekend")
        self.assertEqual(weekend["state"],"paused-outside-user-trading-window")
        self.assertEqual(weekend["status"],"not-yet-observed")
        self.assertEqual(weekend["profilesObserved"],0)
        monday = ev.latest(conn,now_ms=1000000,session_mode="trading")
        self.assertEqual(monday["state"],"no-post-commit-capture-observed")
        self.assertEqual(monday["status"],"not-yet-observed")
        self.assertIn("cannot establish a worker outage",monday["note"])

    def test_stale_telemetry_and_unknown_data_remain_unconfirmed(self):
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(760.,{
            "profiles":[{"profile":"balanced","outcome":"evaluation-error",
                         "ready":False,"priceFresh":False,
                         "dataAt":float("nan"),"secret":"DO-NOT-EXPOSE"}]})
        info=ev.latest(conn,now_ms=1000000,session_mode="trading")
        self.assertEqual(info["state"],"last-capture-not-current")
        self.assertEqual(info["profilesChecked"],0)
        self.assertEqual(info["profilesFreshReady"],0)
        self.assertIsNone(info["profiles"][0]["originalDataAt"])
        self.assertNotIn("DO-NOT-EXPOSE",json.dumps(info))

    def test_database_error_never_exposes_private_message(self):
        conn=Mock()
        conn.transaction.return_value=_Tx()
        conn.execute.side_effect=RuntimeError("SECRETS")
        info=ev.latest(conn,now_ms=1000000,session_mode="trading")
        self.assertEqual(info["status"],"unavailable")
        self.assertNotIn("SECRETS",json.dumps(info))

    def test_recent_capture_with_missing_profiles_is_partial_not_verified(self):
        conn=Mock();conn.transaction.return_value=_Tx()
        conn.execute.return_value.fetchone.return_value=(999.,{"profiles":[
            {"profile":"conservative","outcome":"checked","ready":True,
             "priceFresh":False,"dataAt":980000,"barAt":950000}]})
        info=ev.latest(conn,now_ms=1000000,session_mode="trading")
        self.assertEqual(info["state"],"recent-capture-partial-profile-coverage")
        self.assertEqual(info["profilesObserved"],1)
        self.assertEqual(info["profilesFreshReady"],0)
        from bob_diagnostics import simulation_evidence_snapshot
        data=simulation_evidence_snapshot({"status":"observed","accounts":_case(),
            "paperInputLatest":info})
        self.assertEqual(data["paperInputLatest"]["state"],info["state"])
        self.assertEqual(data["paperInputLatest"]["profiles"][0]["profile"],"conservative")

    def test_gap_review_does_not_promote_worker_input_into_trade_outcome(self):
        corr={"recentRecordedGapInstants":[{"recordedAt":1000000,"affectedVirtualCases":2}]}
        source={"items":[{"eventAt":1000000,"state":"nearby-original-observed",
                  "nearestSourceAt":999000,"deltaSeconds":1,
                  "timeRelation":"before-or-at-event"}]}
        worker={"items":[{"eventAt":1000000,"state":"worker-input-captured-near-gap",
                  "capturedAt":1001000,"timeRelation":"after-event",
                  "profiles":[{"profile":"conservative","outcome":"checked","ready":True,
                               "priceFresh":True,"dataAt":999000,"barAt":990000,
                               "secret":"secret-never-out"}]}]}
        import paper_gap_triage
        result=paper_gap_triage.assess(corr,source,{"items":[]},worker)
        self.assertEqual(result["counts"]["workerCaptureOnlyAfterGap"],1)
        item=result["items"][0]
        self.assertEqual(item["paperWorkerEvidence"],"worker-capture-only-after-gap")
        self.assertFalse(item["executedExitVerified"])
        self.assertFalse(item["profitOrLossVerified"])
        self.assertNotIn("secret-never-out",json.dumps(result))
        sample={"status":"observed","accounts":_case(),"paperInputArchive":worker}
        projected=bob_diagnostics.simulation_evidence_snapshot(sample)
        self.assertEqual(projected["paperInputArchive"]["items"][0]["profiles"][0]["profile"],"conservative")
        self.assertNotIn("secret-never-out",json.dumps(projected))


if __name__ == "__main__":
    unittest.main()
