"""No accidental repair, trade or deployment claims from sampled observations."""
import json
import unittest
from diagnostic_state_compare import compare

CURRENT = "b" * 40
OLD = "a" * 40


def event(at, build=CURRENT, status="ok", bad=None, extra=None):
    return {"stage":"health", "observedAt":at, "build":build,
            "payload":{"status":status, "session":"trading",
                       "badCodes":list(bad or []), **(extra or {})}}


class CompareTests(unittest.TestCase):
    def test_two_snapshots_report_only_observed_change(self):
        result=compare([
            event(2000, bad=["market-feed-not-current"]),
            event(1000, bad=["background-worker-stopped"]),
        ])
        state=result["stateComparison"]
        self.assertEqual(state["status"],"observed-comparison")
        self.assertEqual(state["newTechnicalCodes"],["market-feed-not-current"])
        self.assertEqual(state["clearedTechnicalCodes"],["background-worker-stopped"])
        self.assertFalse(state["isRepairVerified"])
        self.assertTrue(state["possibleRegression"])
        self.assertEqual(result["deploymentComparison"]["status"],"insufficient-evidence")

    def test_different_build_does_not_prove_deployment_caused_failure(self):
        result=compare([
            event(2000,build=CURRENT,status="degraded",bad=["market-worker-stopped"]),
            event(1800,build=CURRENT,status="ok"),
            event(1000,build=OLD,status="ok"),
        ])
        self.assertEqual(result["stateComparison"]["previousAt"],1800)
        deployment=result["deploymentComparison"]
        self.assertEqual(deployment["previousBuild"],OLD)
        self.assertEqual(deployment["currentBuild"],CURRENT)
        self.assertTrue(deployment["possibleRegression"])
        self.assertFalse(deployment["isDeploymentRegressionVerified"])
        self.assertFalse(deployment["isRepairVerified"])

    def test_no_samples_old_same_clock_or_missing_build_stays_inconclusive(self):
        self.assertEqual(compare([])["stateComparison"]["status"],"insufficient-evidence")
        self.assertEqual(compare([event(2000)])["stateComparison"]["status"],"insufficient-evidence")
        out=compare([event(2000), event(2000,build=OLD)])
        self.assertEqual(out["stateComparison"]["status"],"insufficient-evidence")
        self.assertEqual(out["deploymentComparison"]["status"],"insufficient-evidence")
        out=compare([event(2000,build="bad"),event(1000,build=OLD)])
        self.assertEqual(out["stateComparison"]["status"],"observed-comparison")
        self.assertEqual(out["deploymentComparison"]["status"],"insufficient-evidence")

    def test_never_echo_private_data_or_malformed_status(self):
        result=compare([
            event(2000,status="password=do-not-expose",
                  bad=["PRIVATE ACCOUNT", "market-feed-not-current"],
                  extra={"token":"SECRET","trade":{"isin":"DO-NOT-LEAK"}}),
            event(1000,build=OLD,status="ok",bad=["untrusted broker-key"]),
            {"stage":"push","observedAt":3000,"payload":{"secret":"NEVER"}},
        ])
        encoded=json.dumps(result)
        for secret in ("do-not-expose","PRIVATE ACCOUNT","SECRET","DO-NOT-LEAK",
                       "untrusted broker-key", "NEVER"):
            self.assertNotIn(secret,encoded)
        self.assertEqual(result["stateComparison"]["currentHealth"],"unknown")
        self.assertEqual(result["stateComparison"]["newTechnicalCodes"],
                         ["market-feed-not-current"])
        self.assertFalse(result["stateComparison"]["isRepairVerified"])

    def test_diagnostic_collector_retains_only_bounded_results(self):
        from bob_diagnostics import collect
        data = compare([event(2000,build=CURRENT),
                        event(1000,build=OLD,status="degraded")])
        report = collect({"simulationAndPush": lambda: {
            "status": "observed",
            "history": {"status": "observed", "areas": {
                "journal": {"status": "observed",
                            "stateComparison": data["stateComparison"],
                            "deploymentComparison": data["deploymentComparison"],
                            "events": [{"secret": "DO-NOT-PUBLISH"}]}}},
        }})
        area = report["areas"]["historicalComparisons"]
        self.assertEqual(area["status"], "observed")
        self.assertEqual(area["deploymentComparison"]["previousBuild"], OLD)
        self.assertNotIn("DO-NOT-PUBLISH", json.dumps(area))
        # A short report that cannot show a prior health event fails closed.
        no_old = collect({"simulationAndPush": lambda: {
            "status": "observed", "history": {"status": "observed",
              "areas": {"journal": {"status": "warming",
                "stateComparison": {"status": "insufficient-evidence"}}}}}})
        self.assertEqual(no_old["areas"]["historicalComparisons"]["status"],
                         "insufficient")

    def test_missing_or_invalid_code_list_never_fakes_cleared_or_added_codes(self):
        known = event(1000, bad=["market-worker-stopped"])
        missing = event(2000)
        del missing["payload"]["badCodes"]
        result = compare([missing, known])
        sampled = result["stateComparison"]
        self.assertEqual(sampled["status"], "observed-comparison")
        self.assertEqual(sampled["codeDeltaStatus"], "insufficient-evidence")
        self.assertEqual(sampled["newTechnicalCodes"], [])
        self.assertEqual(sampled["clearedTechnicalCodes"], [])
        self.assertEqual(sampled["regressionAssessment"], "insufficient-evidence")
        self.assertFalse(sampled["possibleRegression"])
        self.assertFalse(sampled["isRepairVerified"])
        invalid = event(2000, bad=["market-worker-stopped", "SECRET_USER"])
        after = compare([invalid, known])["stateComparison"]
        self.assertEqual(after["codeDeltaStatus"], "insufficient-evidence")
        self.assertNotIn("SECRET_USER", json.dumps(after))
        too_many = event(2000, bad=["market-worker-stopped"] * 21)
        self.assertEqual(compare([too_many, known])["stateComparison"][
            "codeDeltaStatus"], "insufficient-evidence")

    def test_weekend_is_not_a_trading_deployment_regression_or_recovery(self):
        before = event(1000, build=OLD, status="ok",
                       bad=["market-feed-not-current"], extra={"session":"trading"})
        after = event(2000, build=CURRENT, status="degraded",
                      bad=[], extra={"session":"weekend"})
        result = compare([after, before])["deploymentComparison"]
        self.assertEqual(result["status"], "observed-comparison")
        self.assertFalse(result["sessionComparable"])
        self.assertEqual(result["codeDeltaStatus"], "insufficient-evidence")
        self.assertFalse(result["possibleRegression"])
        self.assertEqual(result["regressionAssessment"], "insufficient-evidence")
        self.assertFalse(result["observationsAreDeploymentOrder"])
        self.assertEqual(result["clearedTechnicalCodes"], [])
        self.assertFalse(result["isDeploymentRegressionVerified"])

    def test_same_session_confirmed_new_code_is_review_lead_not_causal_fix(self):
        before = event(1000,build=OLD,status="ok",bad=[])
        after = event(2000,build=CURRENT,status="degraded",
                      bad=["research-worker-stopped"])
        result = compare([after,before])["deploymentComparison"]
        self.assertTrue(result["sessionComparable"])
        self.assertEqual(result["codeDeltaStatus"], "observed")
        self.assertTrue(result["possibleRegression"])
        self.assertEqual(result["regressionAssessment"],
                         "possible-in-observed-sample")
        self.assertFalse(result["isDeploymentRegressionVerified"])
        self.assertFalse(result["observationsAreDeploymentOrder"])

    def test_unknown_session_fails_closed_for_health_delta(self):
        before = event(1000, status="ok")
        before["payload"].pop("session")
        after = event(2000, status="degraded",
                      bad=["market-feed-not-current"])
        result = compare([after,before])["stateComparison"]
        self.assertEqual(result["codeDeltaStatus"], "insufficient-evidence")
        self.assertFalse(result["possibleRegression"])
        self.assertIsNone(result["previousSession"])
        self.assertEqual(result["regressionAssessment"], "insufficient-evidence")

    def test_out_of_order_and_invalid_rows_are_bounded(self):
        rows=[event(1000,build=OLD),event(3000),event(2000)] + [
            {"stage":"health","observedAt":float("nan"),"payload":{"status":"ok"}},
            {"stage":"health","observedAt":4000,"payload":"SECRET"}]
        result=compare(rows)
        self.assertEqual(result["stateComparison"]["currentAt"],3000)
        self.assertEqual(result["stateComparison"]["previousAt"],2000)
        self.assertEqual(result["deploymentComparison"]["previousAt"],1000)
        self.assertEqual(result["sampledHealthEvents"],3)


if __name__=="__main__":
    unittest.main()
