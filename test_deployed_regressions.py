import tempfile
import unittest
from pathlib import Path
from tools.bob_deployed_regressions import ASSETS, verify_assets, read_asset

class DeployedRegressionTests(unittest.TestCase):
    def test_exact_assets_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ASSETS:(root/name).write_bytes(name.encode())
            self.assertTrue(verify_assets(lambda name:name.encode(),root))
            self.assertFalse(verify_assets(lambda name:b'<html>Login</html>',root))
            self.assertFalse(verify_assets(lambda name:b'old-code' if name==ASSETS[-1] else name.encode(),root))

    def test_no_unlisted_urls(self):
        with self.assertRaises(ValueError):read_asset('../api/private')
