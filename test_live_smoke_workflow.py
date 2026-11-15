from pathlib import Path
import unittest


WORKFLOW = Path(__file__).parent / ".github/workflows/bob-live-smoke.yml"


class LiveSmokeWorkflowTests(unittest.TestCase):
    def test_protected_shell_retries_without_weakening_auth_contract(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        shell_check = source.split("shell_ok=0", 1)[1]

        self.assertIn("for n in 1 2 3 4; do", shell_check)
        self.assertIn('[ "$code" = "303" ]', shell_check)
        self.assertIn("grep -Eiq '^Location: /login'", shell_check)
        self.assertIn('test "$shell_ok" = "1"', shell_check)
        self.assertIn("status=${code:-curl-error}", shell_check)
        self.assertNotIn('test "$code" = "200"', shell_check)


if __name__ == "__main__":
    unittest.main()
