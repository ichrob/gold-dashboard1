"""Regression checks for Bob's eight-area status overview."""
import re
import shutil
import subprocess
import unittest

import bob_area_checks


class WholeAppAreaChecksTests(unittest.TestCase):
    def setUp(self):
        self.html = bob_area_checks.PANEL
        match = re.search(r"<script>(.*?)</script>", self.html, flags=re.S)
        self.assertIsNotNone(match)
        self.javascript = match.group(1)

    def test_all_eight_navigation_areas_are_checked(self):
        for key in ("overview", "products", "trade", "auto", "future",
                    "research", "learning", "problems"):
            self.assertIn(f"['{key}',", self.javascript)
        self.assertIn("bob-view-", self.javascript)
        self.assertIn("bob-area-check-marker", self.javascript)

    def test_honest_fail_closed_evidence_states(self):
        self.assertIn("ok:'✓'", self.javascript)
        self.assertIn("warning:'⚠'", self.javascript)
        self.assertIn("unknown:'?'", self.javascript)
        self.assertIn("audit.incomplete===0", self.javascript)
        self.assertIn("live?.status==='fresh'", self.javascript)
        self.assertIn("validBars", self.javascript)
        self.assertIn("sourceAge", self.javascript if "sourceAge" in self.javascript else "sourceAge")
        self.assertIn("out.auto=say('unknown'", self.javascript)
        self.assertIn("out.learning=say('unknown'", self.javascript)
        self.assertIn("issues===null", self.javascript)
        self.assertIn("last=out;at=Date.now();render(out);", self.javascript)

    def test_only_reads_existing_endpoints_and_has_no_trade_actions(self):
        for endpoint in ("/health", "/health/background", "/api/live",
                         "/api/degiro/audit", "/api/gold-research",
                         "/api/zukunft/research", "/api/problems"):
            self.assertIn("read('" + endpoint + "'", self.javascript)
        self.assertIn("credentials:'same-origin'", self.javascript)
        self.assertIn("cache:'no-store'", self.javascript)
        for forbidden in ("method:'POST'", "buyOrder(", "sellOrder(",
                          "localStorage.setItem", "Notification.requestPermission"):
            self.assertNotIn(forbidden, self.javascript)

    @unittest.skipUnless(shutil.which("node"), "node runtime unavailable")
    def test_embedded_javascript_syntax(self):
        proc = subprocess.run(
            ["node", "--check", "-"], input=self.javascript,
            capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
