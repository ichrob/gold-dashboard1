"""Check the injected risk/exit panel JS as a real script, not as HTML markup."""
import re
import shutil
import subprocess
import unittest
import trade_review_panel


class TradePanelSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js missing')
    def test_mobile_panel_is_valid_javascript(self):
        match=re.search(r'<script>(.*?)</script>',trade_review_panel.PANEL,re.S)
        self.assertIsNotNone(match)
        result=subprocess.run(['node','--check'],input=match.group(1),
            text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
