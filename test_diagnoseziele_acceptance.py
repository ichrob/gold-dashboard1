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
        self.assertEqual(result["status"],"five-dated-independent-acceptances")
        self.assertEqual(result["acceptedGoalIds"],[2,7,8,13,18])
        self.assertEqual(result["individuallyAcceptedAtRecordedBuild"],1)
        self.assertEqual(result["remainingUnaccepted"],95)
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

    def test_render_metric_acceptance_requires_both_services_and_both_series(self):
        goals, records = self.fixtures()
        valid = a.assess(goals, records)
        self.assertEqual(valid["individuallyAcceptedAtRecordedMetricWindow"], 1)
        self.assertEqual(valid["metricSampleWindow"]["services"], 2)
        self.assertEqual(valid["metricSampleWindow"]["resolutionSeconds"], 300)
        self.assertFalse(valid["continuouslyHealthyProven"])
        mutations = (
            lambda r: r["accepted"][1]["services"][0].update(cpuObservations=0),
            lambda r: r["accepted"][1]["services"][1].update(memoryObservations=0),
            lambda r: r["accepted"][1]["services"][0].update(cpuCoreMin=2.),
            lambda r: r["accepted"][1]["services"][0].update(memoryBytesMax=-1),
            lambda r: r["accepted"][1]["services"][1].update(service="bob-private-scanner"),
            lambda r: r["accepted"][1].update(resolutionSeconds=0),
            lambda r: r["accepted"][1].update(source="UNVERIFIED"),
            lambda r: r["accepted"][1].update(windowEnd="2026-10-25T09:00:00Z"),
        )
        for mutation in mutations:
            changed=json.loads(json.dumps(records))
            mutation(changed)
            self.assertEqual(a.assess(goals,changed)["status"],"unavailable")

    def test_13_and_18_are_only_accepted_ids(self):
        goals,records=self.fixtures()
        for index in (12,17):
            modified=json.loads(json.dumps(goals))
            modified[index]["verified"]=False
            self.assertEqual(a.assess(modified,records)["status"],"unavailable")
        injected=json.loads(json.dumps(records))
        injected["accepted"][1]["id"]=19
        self.assertEqual(a.assess(goals,injected)["status"],"unavailable")

    def test_real_historical_health_pair_is_dated_and_ignores_missing_proof(self):
        goals, record = self.fixtures()
        result = a.assess(goals, record)
        self.assertEqual(result["individuallyAcceptedAtArchivedHealthPair"], 1)
        self.assertEqual(result["healthPairSample"]["session"], "weekend")
        self.assertFalse(result["healthPairSample"]["causalRepairVerified"])
        self.assertFalse(result["continuouslyHealthyProven"])
        self.assertTrue(result["healthPairSample"]["previousAt"] <
                        result["healthPairSample"]["currentAt"])
        def mutate(fn):
            clone=json.loads(json.dumps(record))
            fn(clone["accepted"][2])
            self.assertEqual(a.assess(goals,clone)["status"],"unavailable")
        cases=(
            lambda r:r.update(kind="just-a-test"),
            lambda r:r.update(source="unverified"),
            lambda r:r.update(build="main"),
            lambda r:r["github"].update(ciConclusion="pending"),
            lambda r:r["sourceReport"].update(previousBuild="c"*40),
            lambda r:r["sourceReport"].update(currentSession="trading"),
            lambda r:r["sourceReport"].update(codeDeltaStatus="insufficient-evidence"),
            lambda r:r["sourceReport"].update(isRepairVerified=True),
            lambda r:r["sourceReport"].update(isDeploymentRegressionVerified=True),
            lambda r:r["sourceReport"].update(previousAt=99999999999),
            lambda r:r["sourceReport"].update(currentAt=None),
            lambda r:r.update(observedAt="2026-10-24T08:00:00Z"),
        )
        for case in cases:
            with self.subTest(case=str(case)):
                mutate(case)

    def test_only_7_8_13_18_may_be_accepted_even_when_count_agrees(self):
        goals,record=self.fixtures()
        for index in (6, 7, 12, 17):
            mutated=json.loads(json.dumps(goals))
            mutated[index]["state"]="partial"
            mutated[index]["verified"]=False
            self.assertEqual(a.assess(mutated,record)["status"],"unavailable")
        mutated=json.loads(json.dumps(goals))
        mutated[7]["state"]="partial"
        mutated[7]["verified"]=False
        self.assertEqual(a.assess(mutated,record)["status"],"unavailable")
        forgery=json.loads(json.dumps(record))
        forgery["accepted"][2]["id"]=19
        self.assertEqual(a.assess(goals,forgery)["status"],"unavailable")

    def test_archived_seven_day_stage_sample_has_original_provider_bounds(self):
        goals, records = self.fixtures()
        result = a.assess(goals, records)
        self.assertEqual(result["individuallyAcceptedAtArchivedStageWindow"], 1)
        self.assertEqual(result["stageWindowSample"]["totalSampled"], 100)
        self.assertEqual(result["stageWindowSample"]["limitPerStage"], 20)
        self.assertEqual(result["stageWindowSample"]["counts"]["health"], 20)
        self.assertEqual(result["stageWindowSample"]["counts"]["push-delivery"], 0)
        self.assertFalse(result["stageWindowSample"]["handsetDeliveryVerified"])
        self.assertFalse(result["stageWindowSample"]["paperExecutionVerified"])
        self.assertFalse(result["stageWindowSample"]["noRecordedEventMeansNoRealEvent"])
        self.assertFalse(result["continuouslyHealthyProven"])
        self.assertNotIn("private-token", json.dumps(result))

    def test_stage_sample_missing_truncated_or_forged_status_fails_closed(self):
        goals, records = self.fixtures()
        def check(edit):
            mutated=json.loads(json.dumps(records))
            edit(mutated["accepted"][3])
            self.assertEqual(a.assess(goals, mutated)["status"], "unavailable")
        invalid = (
            lambda r: r.update(id=19),
            lambda r: r.update(kind="test-file-exists"),
            lambda r: r.update(source="user-supplied-data"),
            lambda r: r.update(build="main"),
            lambda r: r.update(observedAt="no clock"),
            lambda r: r["github"].update(ciConclusion="in_progress"),
            lambda r: r["github"].update(liveSmokeRun=0),
            lambda r: r["sample"].update(status="warming"),
            lambda r: r["sample"].update(scope="all-market-orders"),
            lambda r: r["sample"].update(limitPerStage=250),
            lambda r: r["sample"].update(totalSampled=999),
            lambda r: r["sample"].update(handsetDeliveryVerified=True),
            lambda r: r["sample"].update(paperExecutionVerified=True),
            lambda r: r["sample"].update(readOnly=False),
            lambda r: r["sample"].update(realOrders=True),
            lambda r: r["sample"]["counts"].update(health=21),
            lambda r: r["sample"]["counts"].update(health=-1),
            lambda r: r["sample"]["counts"].update(health=True),
            lambda r: r["sample"]["counts"].pop("push-delivery"),
            lambda r: r["sample"]["counts"].update(secret="PRIVATE_ACCOUNT"),
        )
        for item in invalid:
            with self.subTest(edit=str(item)):
                check(item)

    def test_goal_7_historical_proof_is_immutable_across_dated_sources(self):
        """A plausible but unobserved time, SHA or CI run is not evidence."""
        goals, records = self.fixtures()
        self.assertEqual(a.assess(goals, records)["status"],
                         "five-dated-independent-acceptances")
        cases = (
            lambda r: r.update(build="a" * 40),
            lambda r: r.update(observedAt="2099-01-01T00:00:00Z"),
            lambda r: r.update(observedAt="2026-10-25T19:57:07Z"),
            lambda r: r["github"].update(ciRun=40225363270),
            lambda r: r["github"].update(liveSmokeRun=40225363342),
        )
        for change in cases:
            candidate = json.loads(json.dumps(records))
            change(candidate["accepted"][3])
            with self.subTest(change=str(change)):
                self.assertEqual(a.assess(goals, candidate)["status"],
                                 "unavailable")

    def test_root_module_detection_is_dated_not_import_or_health_proof(self):
        goals,records=self.fixtures()
        accepted=a.assess(goals,records)
        self.assertEqual(accepted["individuallyAcceptedAtRootModuleChange"],1)
        sample=accepted["moduleChangeSample"]
        self.assertEqual(sample["recordedSourceModules"],236)
        self.assertEqual(sample["currentlySeenSourceModules"],237)
        self.assertEqual(sample["newPathsNotInBaseline"],1)
        self.assertFalse(sample["runtimeHealthVerified"])
        self.assertFalse(sample["newModulesFunctioningVerified"])
        self.assertFalse(accepted["continuouslyHealthyProven"])
        self.assertEqual(sample["sourceBuild"],
                         "e45f9a2e039eacb3cd9e1e4a247f02d4e430fbb7")

    def test_root_module_record_is_fail_closed_on_mismatches(self):
        goals,records=self.fixtures()
        changes=(
            lambda r:r.update(source="untrusted-screenshot"),
            lambda r:r.update(kind="file-exists-only"),
            lambda r:r.update(build="a"*40),
            lambda r:r.update(observedAt="bad-time"),
            lambda r:r["github"].update(ciConclusion="pending"),
            lambda r:r["github"].update(ciRun=0),
            lambda r:r["github"].update(liveSmokeRun=0),
            lambda r:r["tree"].update(baselineSourceBlobSha="a"*40),
            lambda r:r["tree"].update(newSourceFile="../sensitive.py"),
            lambda r:r["tree"].update(recordedSourceModules=235),
            lambda r:r["tree"].update(currentlySeenSourceModules=200),
            lambda r:r["tree"].update(newPathsNotInBaseline=0),
            lambda r:r["tree"].update(missingPathsFromBaseline=1),
            lambda r:r["tree"]["sourceKinds"].update(py=200),
            lambda r:r["report"].update(status="same-as-recorded-tree"),
            lambda r:r["report"].update(traversal="full-system-and-secrets"),
            lambda r:r["report"].update(realOrders=True),
            lambda r:r["report"].update(readOnly=False),
            lambda r:r["report"].update(runtimeHealthVerified=True),
            lambda r:r["report"].update(newModulesFunctioningVerified=True),
        )
        for mutation in changes:
            case=json.loads(json.dumps(records))
            mutation(case["accepted"][4])
            with self.subTest(mutation=str(mutation)):
                self.assertEqual(a.assess(goals,case)["status"],"unavailable")

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
        self.assertEqual(bob_diagnostics.read_access_coverage(manifest)["verified"],5)


if __name__=="__main__":
    unittest.main()
