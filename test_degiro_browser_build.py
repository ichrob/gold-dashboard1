import unittest
from pathlib import Path
from tools.build_degiro_browser_bridge import BASE, build


class BridgeBuildTest(unittest.TestCase):
    def test_generated_script_matches_shared_parser(self):
        self.assertEqual((BASE / 'bob_degiro_export.user.js').read_text(), build())

    def test_server_serves_and_includes_bridge(self):
        source = (BASE / 'server.py').read_text()
        self.assertIn('<script src="/degiro_browser_bridge.js"></script>', source)
        for name in ('degiro_browser_bridge.js', 'bob_degiro_export.user.js'):
            self.assertIn('"/' + name + '"', source)
            self.assertTrue((BASE / name).is_file())


if __name__ == '__main__':
    unittest.main()
