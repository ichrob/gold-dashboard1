"""Synthetic-only verification of the fixed Termux signed-asset bootstrap.

Never launches Termux, reads secrets, calls the Render API, or touches a
production directory. The test substitutes a temporary HOME and disables
the final execv boundary after compilation.
"""
import base64
import gzip
import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


BRIDGE=pathlib.Path("android_companion/app/src/main/java/ch/bob/degirocompanion/TermuxBridge.kt")
ASSETS=pathlib.Path("android_companion/app/src/main/assets")
OLD_GIT_BLOB="c506752139eb85487bab7ddd5dc8b0e1da46204c"


def source():
    text=BRIDGE.read_text(encoding="utf-8")
    assert 'private val INSTALL_AND_START = """' in text
    code=text.split('private val INSTALL_AND_START = """',1)[1].split('""".trimIndent()',1)[0]
    # Replace only the fixed final launch; this test exercises installation.
    footer="os.execv(sys.executable,(sys.executable,str(dest/names[1])))"
    assert code.count(footer)==1
    assert "LEGACY_RENDER_BLOB='"+OLD_GIT_BLOB+"'" in code
    code=code.replace(footer,"pass")
    compile(code,"<bundled-offline-bootstrap>","exec")
    return code


class SignedAssetUpgradeTests(unittest.TestCase):
    def argv(self):
        args=["termux-asset-bootstrap"]
        for name in ("bob_offline_key_escrow.py","bob_render_to_offline_escrow.py"):
            data=(ASSETS/name).read_bytes()
            args.extend([base64.b64encode(gzip.compress(data)).decode("ascii"),
                         hashlib.sha256(data).hexdigest()])
        return args

    def test_checked_assets_are_exact_project_sources(self):
        for name in ("bob_offline_key_escrow.py","bob_render_to_offline_escrow.py"):
            self.assertEqual((ASSETS/name).read_bytes(),
                             pathlib.Path(name).read_bytes())
        self.assertNotIn("Temporary Render API key",source())

    def test_known_older_script_can_upgrade_without_changing_any_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)
            directory=home/"bob-sicher"
            directory.mkdir()
            old=b"synthetic old signed software only"
            target=directory/"bob_render_to_offline_escrow.py"
            target.write_bytes(old)
            original=directory/"bob-archive-root.vault"
            original.write_bytes(b"synthetic encrypted backup keep unchanged")
            code=source()
            simulated_hash=hashlib.sha1(
                b"blob "+str(len(old)).encode()+b"\x00"+old).hexdigest()
            code=code.replace("LEGACY_RENDER_BLOB='"+OLD_GIT_BLOB+"'",
                              "LEGACY_RENDER_BLOB='"+simulated_hash+"'")
            with patch.object(pathlib.Path,"home",return_value=home), \
                 patch.object(sys,"argv",self.argv()):
                exec(compile(code,"<test-bootstrap>","exec"),{})
            self.assertEqual(target.read_bytes(),
                             (ASSETS/"bob_render_to_offline_escrow.py").read_bytes())
            self.assertEqual(original.read_bytes(),
                             b"synthetic encrypted backup keep unchanged")

    def test_unknown_old_source_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)
            directory=home/"bob-sicher";directory.mkdir()
            target=directory/"bob_render_to_offline_escrow.py"
            target.write_bytes(b"untrusted software contents")
            with patch.object(pathlib.Path,"home",return_value=home), \
                 patch.object(sys,"argv",self.argv()):
                with self.assertRaisesRegex(ValueError,"no overwrite"):
                    exec(compile(source(),"<test-bootstrap>","exec"),{})
            self.assertEqual(target.read_bytes(),b"untrusted software contents")


if __name__=="__main__":
    unittest.main()
