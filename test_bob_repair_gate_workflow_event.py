"""Guard the public-repo repair PR evidence gate against risky event triggers.

Static regression: never execute untrusted PR code or expose repository secrets.
"""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parent / ".github/workflows/bob-repair-evidence-gate.yml"


class RepairEvidenceEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_safe_pr_event_and_expected_activity(self):
        s = self.source
        self.assertRegex(s, r"(?m)^on:\s*\n  pull_request:\s*\n")
        self.assertNotRegex(s, r"(?m)^\s*pull_request_target\s*:")
        self.assertIn("types: [opened, synchronize, reopened, edited, ready_for_review]", s)
        self.assertRegex(s, r"(?m)^  evidence:\s*$")

    def test_read_only_token_and_trusted_main_checkout(self):
        s = self.source
        for line in ("  contents: read", "  issues: read", "  pull-requests: read",
                     "          ref: main", "          persist-credentials: false"):
            self.assertIn(line, s)
        self.assertNotRegex(s, r"(?m)^\s*(?:issues|contents|pull-requests):\s*write\s*$")
        self.assertNotIn("secrets.", s)
        self.assertNotIn("github.event.pull_request.head", s)
        self.assertIn('BOB_PR_NUMBER: ${{ github.event.pull_request.number }}', s)
        self.assertIn("python bob_ai_quality_gate.py", s)
        self.assertIn("test_bob_ai_quality_gate.py test_bob_ai_coordination.py", s)

    def test_evidence_gate_still_checks_pr_data_not_untrusted_code(self):
        import bob_ai_quality_gate
        self.assertIn('return "ordinary-pr"', self._read_gate())
        self.assertNotIn("git checkout", self._read_gate())
        self.assertTrue(callable(bob_ai_quality_gate.inspect))

    @staticmethod
    def _read_gate():
        return (WORKFLOW.parents[2] / "bob_ai_quality_gate.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
