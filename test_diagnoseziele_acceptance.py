"""One independently observed, dated CI and dual-Render build match is accepted.

No other goal is promoted, and dated acceptance never implies the next deploy
is healthy, a trade is approved or missing original market data are recovered.
"""
import json
import unittest
from pathlib import Path

import diagnoseziele_acceptance as a
import bob_diagnostics

ROOT=Path(__file__).resolve().parent


class DatedAcceptanceTests(unittest.TestCase):
    def fixtures(self):
        goals=json.loads((ROOT/"Besser_werden/lesezugriff_100_status.json").read_text())["tasks"]
        records=json.loads((ROOT/"Besser_werden/diagnoseziele_100_abnahmen.json").read_text())
        return goals,records

    def test_one_goal_only_has_ci_and_exact_render_evidence(self):
        goals,record=self.fixtures()
        result=a.assess(goals,record)
        self.assertEqual(result["status"],"one-dated-build-acceptance")
        self.assertEqual(result["acceptedGoalIds"],[18])
        self.assertEqual(result["individuallyAcceptedAtRecordedBuild"],1)
        self.assertEqual(result["remainingUnaccepted"],99)
        self.assertEqual(len(result["acceptedBuild"]),40)
        self.assertTrue(result["readOnly"])
        self.assertFalse(result["currentDeployProven"])
        self.assertFalse(result["continuouslyHealthyProven"])
        self.assertNotIn("service_rows",json.dumps(result))

    def test_any_wrong_service_or_sha_or_missing_ci_fails_closed(self):
        goals,record=self.fixtures()
        mutations=(
            lambda r:r["accepted"][0]["render"][0].update(build="b"*40),
            lambda r:r["accepted"][0]["render"][0].update(status="update_in_progress"),
            lambda r:r["accepted"][0]["render"][1].update(service="bob-private-scanner"),
            lambda r:r["accepted"][0]["render"][1].update(finishedAt="2026-10-26T00:00:00Z"),
            lambda r:r["accepted"][0]["github"].update(ciConclusion="skipped"),
            lambda r:r["accepted"][0]["github"].update(liveSmokeConclusion="failure"),
            lambda r:r["accepted"][0]["github"].update(ciRun=0),
            lambda r:r["accepted"][0].update(build="main"),
            lambda r:r["accepted"][0].update(checkedAt="not a timestamp"),
        )
        for mutation in mutations:
            with self.subTest(mutation=str(mutation)):
                changed=json.loads(json.dumps(record))
                mutation(changed)
                self.assertEqual(a.assess(goals,changed)["status"],"unavailable")

    def test_no_other_goal_can_gain_verified_without_its_own_gate(self):
        goals,record=self.fixtures()
        altered=json.loads(json.dumps(goals))
        altered[0]["verified"]=True
        self.assertEqual(a.assess(altered,record)["status"],"unavailable")
        altered=json.loads(json.dumps(goals))
        altered[17]["verified"]=False
        self.assertEqual(a.assess(altered,record)["status"],"unavailable")
        altered=json.loads(json.dumps(goals))
        altered[17]["state"]="partial"
        self.assertEqual(a.assess(altered,record)["status"],"unavailable")
        changed=json.loads(json.dumps(record))
        changed["accepted"].append(dict(changed["accepted"][0],id=19))
        self.assertEqual(a.assess(goals,changed)["status"],"unavailable")

    def test_read_access_rejects_fake_extra_completions(self):
        goals,record=self.fixtures()
        original=goals[0]["verified"]
        goals[0]["verified"]=True
        manifest=json.loads((ROOT/"Besser_werden/lesezugriff_100_status.json").read_text())
        manifest["tasks"]=goals
        self.assertEqual(bob_diagnostics.read_access_coverage(manifest)["status"],
                         "unavailable")
        goals[0]["verified"]=original
        manifest["tasks"]=goals
        self.assertEqual(bob_diagnostics.read_access_coverage(manifest)["verified"],1)


if __name__=="__main__":
    unittest.main()
