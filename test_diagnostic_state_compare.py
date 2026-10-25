"""No accidental repair, trade or deployment claims from sampled observations."""
import json
import unittest
from diagnostic_state_compare import compare

CURRENT = "b" * 40
OLD = "a" * 40


def event(at, build=CURRENT, status="ok", bad=None, extra=None):
    return {"stage":"health", "observedAt":at, "build":build,
            "payload":{"status":status, "badCodes":list(bad or []), **(extra or {})}}


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
