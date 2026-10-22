"""CI regression: browser hangs must fail closed, never silently release."""
from pathlib import Path
import re
import unittest

CI = (Path(__file__).resolve().parent/'.github/workflows/ci.yml').read_text(encoding='utf-8')

class CIWatchdogTests(unittest.TestCase):
    def test_main_commits_have_independent_release_checks(self):
        self.assertIn("github.event_name == 'push' && github.sha || 'shared'", CI)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", CI)
        self.assertIn('needs: [validate]', CI)
        self.assertIn('if [ "$VALIDATE_RESULT" != "success" ]; then', CI)
        self.assertIn('name: Bob release gate', CI)
        self.assertIn('timeout-minutes: 30', CI)

    def test_browser_dependencies_have_finite_fail_closed_timeouts(self):
        self.assertIn('name: Browser toolchain setup (bounded)', CI)
        self.assertIn('timeout --signal=TERM --kill-after=10s 240s npm install', CI)
        self.assertIn('timeout --signal=TERM --kill-after=10s 300s', CI)
        self.assertIn('timeout --signal=TERM --kill-after=10s 180s sudo apt-get', CI)
        self.assertIn('timeout --signal=TERM --kill-after=10s 40s ffmpeg', CI)

    def test_all_browser_suites_still_run_without_swallowing_failures(self):
        suites = sorted(set(re.findall(r'node (browser_[a-z_]+\.cjs)', CI)))
        self.assertGreaterEqual(len(suites), 13)
        for suite in suites:
            self.assertIn('timeout --signal=TERM --kill-after=10s 120s node '+suite, CI)
        self.assertIn('browser_unified_workspace.cjs', suites)
        self.assertIn('browser_video_evidence.cjs', suites)
        self.assertIn('browser_degiro_all_products.cjs', suites)
        self.assertIn('browser_degiro_candidate_image.cjs', suites)
        # Do not ignore a timeout or continue publishing on browser failures.
        self.assertNotRegex(CI, r'(?m)^\s*NODE_PATH=.*\|\|\s*true\s*$')
        self.assertNotRegex(CI, r'(?m)^\s*NODE_PATH=.*\bcontinue-on-error')

if __name__ == '__main__':
    unittest.main()
