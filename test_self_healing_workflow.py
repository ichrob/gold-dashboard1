import unittest
from pathlib import Path


class SelfHealingWorkflowTriggerTests(unittest.TestCase):
    def test_successful_main_ci_triggers_delayed_existing_watchdog(self):
        workflow = Path(".github/workflows/bob-self-healing.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("  workflow_run:\n", workflow)
        self.assertIn('    workflows: ["Bob CI"]\n', workflow)
        self.assertIn("    types: [completed]\n", workflow)
        self.assertIn("    branches: [main]\n", workflow)
        self.assertIn(
            "github.event.workflow_run.conclusion == 'success'", workflow
        )
        self.assertIn("      - name: Wait for checksPass Render rollout\n", workflow)
        self.assertIn("        run: sleep 120\n", workflow)
        self.assertEqual(
            workflow.count("name: Bob independent self-healing escalation"), 1
        )
        self.assertIn("  schedule:\n", workflow)
        self.assertIn("  workflow_dispatch:\n", workflow)


if __name__ == "__main__":
    unittest.main()
