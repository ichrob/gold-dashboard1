import pathlib
import re
import subprocess
import tempfile
import unittest


class BobPushContractTests(unittest.TestCase):
    def setUp(self):
        self.html = pathlib.Path("Bob.html").read_text(encoding="utf-8")

    def test_two_user_push_controls_are_present(self):
        self.assertIn('id="generalPushBtn"', self.html)
        self.assertIn('id="tradePushBtn"', self.html)
        self.assertIn("togglePush('general')", self.html)
        self.assertIn("togglePush('trade')", self.html)

    def test_trade_management_is_guarded(self):
        self.assertRegex(self.html, r'function canNotify\(kind\).*?kind!=="trade"\\s*\\|\\|\\s*pushState\.activeTrade')
        self.assertIn('if(kind==="trade"&&!pushState.activeTrade)return false;', self.html)

    def test_entry_push_uses_confirmed_signal(self):
        self.assertIn('confirmedSignalDirection()', self.html)
        self.assertIn('notifyGeneral("Bob – "+dir+" Einstiegssignal"', self.html)
        self.assertIn('lastPushedEntryDirection', self.html)

    def test_anti_spam_simulation_and_monitoring_exist(self):
        self.assertIn('const PUSH_COOLDOWN=15*60*1000;', self.html)
        self.assertIn('pushState.simulation', self.html)
        self.assertIn('function monitorActiveTrade()', self.html)
        self.assertIn('notifyTrade("Bob – Risikoalarm"', self.html)
        self.assertIn('notifyTrade("Bob – Trade schließen"', self.html)

    def test_embedded_javascript_parses(self):
        scripts = re.findall(r'<script(?:\\s[^>]*)?>(.*?)</script>', self.html, flags=re.S | re.I)
        self.assertTrue(scripts)
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as f:
            f.write("\\n".join(scripts))
            f.flush()
            result = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
