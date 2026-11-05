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
OLD_RENDER_BLOB="c506752139eb85487bab7ddd5dc8b0e1da46204c"
OLD_OFFLINE_BLOB="65eeeb4506174e3439097909f4bbb153cec8f483"


def source():
    text=BRIDGE.read_text(encoding="utf-8")
    assert 'private val INSTALL_AND_START = """' in text
    code=text.split('private val INSTALL_AND_START = """',1)[1].split('""".trimIndent()',1)[0]
    # Replace only the fixed final launch; this test exercises installation.
    footer="os.execv(sys.executable,(sys.executable,str(dest/names[1])))"
    assert code.count(footer)==1
    assert OLD_RENDER_BLOB in code
    assert OLD_OFFLINE_BLOB in code
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

    def test_both_known_signed_scripts_can_upgrade_without_touching_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=pathlib.Path(tmp)
            directory=home/"bob-sicher"
            directory.mkdir()
            old_render=b"synthetic old signed Render client"
            old_offline=b"synthetic old signed encryption helper"
            render_path=directory/"bob_render_to_offline_escrow.py"
            offline_path=directory/"bob_offline_key_escrow.py"
            render_path.write_bytes(old_render)
            offline_path.write_bytes(old_offline)
            original=directory/"bob-archive-root.vault"
            original.write_bytes(b"synthetic encrypted backup keep unchanged")
            code=source()
            old_render_hash=hashlib.sha1(
                b"blob "+str(len(old_render)).encode()+b"\x00"+old_render).hexdigest()
            old_offline_hash=hashlib.sha1(
                b"blob "+str(len(old_offline)).encode()+b"\x00"+old_offline).hexdigest()
            code=code.replace(OLD_RENDER_BLOB,old_render_hash)
            code=code.replace(OLD_OFFLINE_BLOB,old_offline_hash)
            with patch.object(pathlib.Path,"home",return_value=home), \
                 patch.object(sys,"argv",self.argv()):
                exec(compile(code,"<test-bootstrap>","exec"),{})
            self.assertEqual(render_path.read_bytes(),
                             (ASSETS/"bob_render_to_offline_escrow.py").read_bytes())
            self.assertEqual(offline_path.read_bytes(),
                             (ASSETS/"bob_offline_key_escrow.py").read_bytes())
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
