"""Sunday/Monday handoff covers all goals, but cannot claim completed trades."""
import json
import unittest
from copy import deepcopy
from pathlib import Path

import diagnoseziele_work_split as split
import bob_diagnostics as diag

ROOT=Path(__file__).resolve().parent


class WeekendHandoffTests(unittest.TestCase):
    def fixtures(self):
        goals=json.loads((ROOT/'Besser_werden/lesezugriff_100_status.json')
                         .read_text(encoding='utf-8'))["tasks"]
        plan=json.loads((ROOT/'Besser_werden/sonntag_montag_100_plan.json')
                        .read_text(encoding='utf-8'))
        return goals,plan

    def test_complete_exact_100_and_four_independent_acceptances(self):
        goals,plan=self.fixtures()
        got=split.assess(goals,plan)
        self.assertEqual(got["status"],"complete-planning-coverage")
        self.assertEqual(got["totalGoals"],100)
        self.assertEqual(got["individuallyAcceptedAtDatedSample"],4)
        self.assertEqual(got["notIndividuallyAccepted"],96)
        self.assertEqual(got["weekendReviewCandidateGoals"],94)
        self.assertEqual(got["originalMarketProofContingentGoals"],41)
        self.assertEqual(sum(g["total"] for g in got["groups"]),100)
        self.assertEqual(sum(g["notAccepted"] for g in got["groups"]),96)
        self.assertEqual(got["deviceRequiredGoalIds"],[91,92,93,94,95])
        self.assertEqual(got["clientBlockedGoalIds"],[1])
        self.assertTrue(got["readOnly"])
        self.assertFalse(got["realOrders"])
        self.assertTrue(got["noMarketDataInferred"])
        self.assertTrue(got["noPhoneActionsInferred"])
        self.assertNotIn("tradeApproved",json.dumps(got))
        self.assertNotIn("orderExecuted",json.dumps(got))

    def test_group_counts_are_individual_not_fake_overall_acceptance(self):
        goals,plan=self.fixtures()
        expected={"client-provider-schema":1,"device-local":5,
                  "market-original-clock":41,"broker-issuer-source":22,
                  "external-research-media":7,"independent-code-and-runtime":24}
        got=split.assess(goals,plan)
        for row in got["groups"]:
            self.assertEqual(row["total"],expected[row["code"]])
            self.assertEqual(row["acceptedHistorically"],
                             4 if row["code"]=="independent-code-and-runtime" else 0)
        manifest=json.loads((ROOT/'Besser_werden/lesezugriff_100_status.json')
                            .read_text(encoding='utf-8'))
        private=diag.read_access_coverage(manifest)
        self.assertEqual(private["verified"],4)
        self.assertEqual(private["workSplit"],got)

    def test_missing_duplicate_or_out_of_scope_goal_is_refused(self):
        goals,base=self.fixtures()
        mutations=(
            lambda p:p["groups"][1]["ids"].append(1),
            lambda p:p["groups"][1]["ids"].pop(),
            lambda p:p["groups"][2]["ids"].append(101),
            lambda p:p["groups"][2]["ids"].append(11),
            lambda p:p["groups"][0].update(code="private-broker-trade"),
            lambda p:p["groups"][0].update(code="market-original-clock"),
            lambda p:p["groups"][2].update(marketWindowNotRequired=True),
            lambda p:p["groups"][2].update(marketWindowNotRequired="false"),
            lambda p:p["groups"][0].update(ids=[91]),
            lambda p:p.update(scope="all-goals-verified"),
            lambda p:p.update(asOf="not-a-date"),
            lambda p:p.update(schemaVersion=3),
            lambda p:p["safety"].update(realOrders=True),
            lambda p:p["safety"].update(deviceControlWithoutConsent=True),
            lambda p:p["safety"].update(emailsWithoutConsent=True),
        )
        for mutation in mutations:
            altered=deepcopy(base)
            mutation(altered)
            with self.subTest(mutation=str(mutation)):
                self.assertEqual(split.assess(goals,altered)["status"],"unavailable")

    def test_invented_goal_verification_or_device_closure_fails_closed(self):
        goals,plan=self.fixtures()
        altered=deepcopy(goals)
        altered[10]["verified"]=True
        self.assertEqual(split.assess(altered,plan)["status"],"unavailable")
        altered=deepcopy(goals)
        altered[90]["state"]="verified-at-sample"
        self.assertEqual(split.assess(altered,plan)["status"],"unavailable")
        altered=deepcopy(goals)
        altered[0]["state"]="partial"
        self.assertEqual(split.assess(altered,plan)["status"],"unavailable")
        altered=deepcopy(goals)
        altered[0]["id"]=None
        self.assertEqual(split.assess(altered,plan)["status"],"unavailable")

    def test_user_supplied_text_is_never_published_in_private_summary(self):
        goals,plan=self.fixtures()
        plan["groups"][2]["sundayScope"]="secret-password-DONT-ECHO"
        plan["groups"][2]["nextGate"]="bank-account-DONT-ECHO"
        got=split.assess(goals,plan)
        self.assertEqual(got["status"],"complete-planning-coverage")
        self.assertNotIn("DONT-ECHO",json.dumps(got))


if __name__=="__main__":
    unittest.main()
