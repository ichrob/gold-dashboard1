import unittest
from pathlib import Path


class SelfHealingWorkflowTriggerTests(unittest.TestCase):
    def test_main_live_smoke_completion_triggers_existing_watchdog(self):
        workflow = Path(".github/workflows/bob-self-healing.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("  workflow_run:\n", workflow)
        self.assertIn('    workflows: ["Bob live smoke test"]\n', workflow)
        self.assertIn("    types: [completed]\n", workflow)
        self.assertIn("    branches: [main]\n", workflow)
        self.assertEqual(
            workflow.count("name: Bob independent self-healing escalation"), 1
        )
        self.assertIn("  schedule:\n", workflow)
        self.assertIn("  workflow_dispatch:\n", workflow)


if __name__ == "__main__":
    unittest.main()
