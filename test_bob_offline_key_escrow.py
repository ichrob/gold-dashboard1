"""Synthetic-only offline escrow tests. No production key ever appears here."""
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bob_offline_key_escrow as escrow
import drive_archive_encryption as production


class EscrowTests(unittest.TestCase):
    ROOT = "synthetic-test-secret-only-" + "Z" * 48
    PASSWORD = "independent strong synthetic offline passphrase 2026"

    def test_old_archive_opens_with_separate_escrow_after_active_root_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            vault = d / "secret.vault"
            state = escrow.create_escrow(self.ROOT.encode(), self.PASSWORD, vault)
            self.assertFalse(state["independentOfflineRetentionVerified"])
            self.assertEqual(stat.S_IMODE(vault.stat().st_mode), 0o600)
            self.assertNotIn(self.ROOT, vault.read_text())
            original = d / "archive.zip"
            original.write_bytes(os.urandom(1024 * 1024 + 3))
            digest = hashlib.sha256(original.read_bytes()).hexdigest()
            encrypted = d / "archive.zip.aesgcm"
            with patch.dict(os.environ, {"PUSH_SERVICE_TOKEN": self.ROOT}):
                production.seal(original, encrypted, digest)
            with patch.dict(os.environ, {"PUSH_SERVICE_TOKEN": "rotated-" + "X"*48}):
                root = escrow.unlock_escrow(vault, self.PASSWORD)
                proof = escrow.verify_archive(encrypted, root, digest)
            self.assertTrue(proof["encryptedOriginalAuthenticated"])
            self.assertTrue(proof["originalSha256Verified"])
            self.assertFalse(proof["offlineBackupDurabilityVerified"])
            self.assertFalse(proof["independentPostgresRestorePerformed"])
            self.assertNotIn(self.ROOT, json.dumps(proof))

    def test_cli_create_accepts_utf8_passphrase_without_exposing_it(self):
        import io
        import sys
        password="Unabhängig-Sicherung-äöü🔒-Lang-2026"
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"offline.vault"
            result=io.StringIO()
            with patch.object(sys,"argv",["escrow","create","--output",str(output)]), \
                 patch("getpass.getpass",side_effect=[
                     self.ROOT,self.ROOT,password,password]), \
                 patch("sys.stdout",new=result):
                self.assertEqual(escrow.main(),0)
            self.assertEqual(escrow.unlock_escrow(output,password),self.ROOT.encode())
            self.assertNotIn(password,result.getvalue())
            self.assertNotIn(password,output.read_text())

    def test_wrong_password_tampered_key_and_repeat_write_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "v"
            escrow.create_escrow(self.ROOT.encode(), self.PASSWORD, vault)
            with self.assertRaises(ValueError):
                escrow.unlock_escrow(vault, "this is an incorrect password")
            record = json.loads(vault.read_text())
            record["nonce"] = record["salt"]
            vault.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                escrow.unlock_escrow(vault, self.PASSWORD)
            with self.assertRaises(FileExistsError):
                escrow.create_escrow(self.ROOT.encode(), self.PASSWORD, vault)

    def test_archive_corruption_and_bad_digest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); original=d/"original"; original.write_bytes(os.urandom(3211))
            sha=hashlib.sha256(original.read_bytes()).hexdigest()
            ciphertext=d/"cipher"
            with patch.dict(os.environ, {"PUSH_SERVICE_TOKEN": self.ROOT}):
                production.seal(original,ciphertext,sha)
            with self.assertRaises(ValueError):
                escrow.verify_archive(ciphertext,self.ROOT.encode(),"0"*64)
            changed=bytearray(ciphertext.read_bytes()); changed[45]^=1
            ciphertext.write_bytes(changed)
            with self.assertRaises(ValueError):
                escrow.verify_archive(ciphertext,self.ROOT.encode(),sha)

    def test_receipt_never_grants_deletion_or_assumes_offline_escrow(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"receipt.json"
            record={"version":"bob-evidence-archive-v3",
                    "scope":escrow.SCOPE,
                    "encryptionVerified":True,
                    "encryptionVersion":escrow.ARCHIVE_VERSION,
                    "remoteDownloadVerified":True,"restoreVerified":True,
                    "restoreIsolation":"separate-database-instance",
                    "deletionPermitted":False,
                    "archiveSha256":"a"*64}
            p.write_text(json.dumps(record))
            self.assertEqual(escrow.verified_receipt_digest(p),"a"*64)
            record["deletionPermitted"]=True
            p.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                escrow.verified_receipt_digest(p)
            record["deletionPermitted"]=False
            record["restoreVerified"]=False
            p.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                escrow.verified_receipt_digest(p)


if __name__ == "__main__":
    unittest.main()
