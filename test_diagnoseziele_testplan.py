"""Representative test coverage must never be mistaken for live acceptance."""
import json
import tempfile
import unittest
from pathlib import Path

import diagnoseziele_testplan as plan

ROOT = Path(__file__).resolve().parent
GOALS = ROOT / "Besser_werden/lesezugriff_100_status.json"
MAPPING = ROOT / "Besser_werden/diagnoseziele_100_testzuordnung.json"


class TestMappingTests(unittest.TestCase):
    def fixtures(self):
        return (
            json.loads(GOALS.read_text(encoding="utf-8"))["tasks"],
            json.loads(MAPPING.read_text(encoding="utf-8")),
        )

    def test_all_100_representative_test_files_exist_without_live_claims(self):
        goals, mapping = self.fixtures()
        result = plan.assess(ROOT, goals, mapping)
        self.assertEqual(result["status"], "test-candidates-mapped")
        self.assertEqual(result["total"], 100)
        self.assertEqual(result["goalTestCandidatesPresent"], 100)
        self.assertEqual(result["goalTestCandidatesMissing"], 0)
        self.assertGreaterEqual(result["uniqueTestFiles"], 85)
        self.assertEqual(result["individuallyVerified"], 0)
        self.assertEqual(result["individualGoalAssertionsConfirmed"], 0)
        self.assertEqual(result["ciExecutionVerifiedPerGoal"], 0)
        self.assertEqual(result["clientBlockedGoalIds"], [1])
        self.assertEqual(result["deviceRequiredGoalIds"], [91, 92, 93, 94, 95])
        self.assertEqual(sum(result["mappedTestKinds"].values()), 100)
        self.assertTrue(result["readOnly"])

    def test_missing_file_is_partial_not_proof_of_success(self):
        goals, mapping = self.fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for row in mapping["goalEvidence"][1:]:
                (root / row["representativeTest"]).touch()
            result = plan.assess(root, goals, mapping)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["missingGoalIds"], [1])
            self.assertEqual(result["individuallyVerified"], 0)

    def test_path_traversal_and_malformed_mapping_fail_closed(self):
        goals, mapping = self.fixtures()
        for name in ("../secret.py", "/private.py", "test___/bad.py",
                     "test_a.py/../../x", "test_x.pyo"):
            copy = json.loads(json.dumps(mapping))
            copy["goalEvidence"][0]["representativeTest"] = name
            result = plan.assess(ROOT, goals, copy)
            self.assertEqual(result["status"], "unavailable")
        copy = json.loads(json.dumps(mapping))
        copy["goalEvidence"][0]["id"] = 2
        self.assertEqual(plan.assess(ROOT, goals, copy)["status"], "unavailable")
        copy = json.loads(json.dumps(mapping))
        copy["goalEvidence"][0]["id"] = 1
        copy["goalEvidence"][0]["claim"] = "goal-live-verified"
        self.assertEqual(plan.assess(ROOT, goals, copy)["status"], "unavailable")

    def test_cannot_automatically_promote_accepted_goals(self):
        goals, mapping = self.fixtures()
        goals[0]["verified"] = True
        self.assertEqual(plan.assess(ROOT, goals, mapping)["status"], "unavailable")
        goals[0]["verified"] = False
        mapping["testExecution"] = "all-tests-proven-passed"
        self.assertEqual(plan.assess(ROOT, goals, mapping)["status"], "unavailable")

    def test_no_sensitive_metadata_from_untrusted_mapping(self):
        goals, mapping = self.fixtures()
        mapping["token"] = "PRIVATE-SERVER-TOKEN"
        mapping["goalEvidence"][0]["secret"] = "NEVER-RETURN"
        result = plan.assess(ROOT, goals, mapping)
        encoded = json.dumps(result)
        self.assertNotIn("PRIVATE-SERVER-TOKEN", encoded)
        self.assertNotIn("NEVER-RETURN", encoded)
        self.assertEqual(result["status"], "test-candidates-mapped")


if __name__ == "__main__":
    unittest.main()
