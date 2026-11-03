"""AES-256-GCM archives remain authenticated after independent Drive downloads."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import drive_archive_encryption as seal


class StreamingEncryptionTests(unittest.TestCase):
    TOKEN = "private-test-root-not-real-" + "z"*48

    def test_bounded_roundtrip_binary_data_and_no_visible_plaintext(self):
        payload = b"PRIVATE-BINARY-ORIGINAL-DO-NOT-UPLOAD-" + os.urandom(
            3 * 1024 * 1024 + 57)
        import hashlib
        checksum=hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":self.TOKEN}):
            d=Path(folder);plain=d/"original.zip";remote=d/"upload.aesgcm"
            decoded=d/"restore.zip"
            plain.write_bytes(payload)
            result=seal.seal(plain,remote,checksum)
            self.assertEqual(result["plaintextSha256"],checksum)
            self.assertEqual(result["ciphertextBytes"],
                             len(payload)+seal.OVERHEAD)
            self.assertEqual(result["format"],seal.FORMAT)
            self.assertNotIn(b"PRIVATE-BINARY-ORIGINAL-DO-NOT-UPLOAD",
                             remote.read_bytes())
            output=seal.unseal(remote,decoded,checksum)
            self.assertTrue(output["encryptionVerified"])
            self.assertEqual(decoded.read_bytes(),payload)

    def test_ciphertext_mutations_and_wrong_secret_never_leave_usable_restore(self):
        import hashlib
        data=os.urandom(3011)
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":self.TOKEN}):
            d=Path(folder);input=d/"in.zip";encrypted=d/"sealed.aesgcm"
            output=d/"restored.zip"
            input.write_bytes(data)
            checksum=hashlib.sha256(data).hexdigest()
            seal.seal(input,encrypted,checksum)
            with patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":"w"*48}):
                with self.assertRaises(ValueError):
                    seal.unseal(encrypted,output,checksum)
            self.assertFalse(output.exists())
            encrypted_data=bytearray(encrypted.read_bytes())
            encrypted_data[30]^=1
            encrypted.write_bytes(encrypted_data)
            with self.assertRaises(ValueError):
                seal.unseal(encrypted,output,checksum)
            self.assertFalse(output.exists())

    def test_missing_key_or_invalid_hash_never_uploads_archive(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);input=d/"in.zip";output=d/"sealed.aesgcm"
            input.write_bytes(b"some data")
            checksum=hashlib.sha256(b"some data").hexdigest()
            with patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":""}):
                with self.assertRaises(ValueError):
                    seal.seal(input,output,checksum)
            self.assertFalse(output.exists())
            with patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":self.TOKEN}):
                with self.assertRaises(ValueError):
                    seal.seal(input,output,"0"*64)
            self.assertFalse(output.exists())

    def test_escrow_root_recovers_prior_archive_after_active_token_rotation(self):
        import hashlib
        payload=os.urandom(1024 * 1024 + 37)
        checksum=hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{
                "PUSH_SERVICE_TOKEN":self.TOKEN,
                "BOB_ARCHIVE_RECOVERY_ROOT_TOKEN":self.TOKEN}):
            d=Path(folder);src=d/"source.zip";encrypted=d/"backup.aesgcm"
            src.write_bytes(payload)
            seal.seal(src,encrypted,checksum)
            result=seal.verify_recovery(encrypted,checksum)
            self.assertEqual(result["recoveryKeyVerified"],True)
            self.assertEqual(result["encryptionVersion"],seal.FORMAT)
            with patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":"rotated-"+"z"*48}):
                with self.assertRaises(ValueError):
                    seal.unseal(encrypted,d/"active-failed.zip",checksum)
                self.assertFalse((d/"active-failed.zip").exists())
                recovered=d/"recovered.zip"
                self.assertTrue(seal.unseal(encrypted,recovered,checksum,recovery=True)
                                ["encryptionVerified"])
                self.assertEqual(recovered.read_bytes(),payload)

    def test_missing_wrong_or_modified_recovery_key_fails_closed(self):
        import hashlib
        payload=os.urandom(8073)
        checksum=hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{
                "PUSH_SERVICE_TOKEN":self.TOKEN,
                "BOB_ARCHIVE_RECOVERY_ROOT_TOKEN":""}):
            d=Path(folder);src=d/"source.zip";encrypted=d/"backup.aesgcm"
            src.write_bytes(payload)
            seal.seal(src,encrypted,checksum)
            with self.assertRaises(ValueError):
                seal.verify_recovery(encrypted,checksum)
            with patch.dict(os.environ,{"BOB_ARCHIVE_RECOVERY_ROOT_TOKEN":"x"*48}):
                with self.assertRaises(ValueError):
                    seal.verify_recovery(encrypted,checksum)
            broken=bytearray(encrypted.read_bytes());broken[len(seal.MAGIC)+23]^=1
            encrypted.write_bytes(broken)
            with patch.dict(os.environ,{"BOB_ARCHIVE_RECOVERY_ROOT_TOKEN":self.TOKEN}):
                with self.assertRaises(ValueError):
                    seal.verify_recovery(encrypted,checksum)

    def test_inplace_and_oversized_files_are_refused(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ,{"PUSH_SERVICE_TOKEN":self.TOKEN}):
            d=Path(folder);input=d/"src";input.write_bytes(b"source")
            with self.assertRaises(ValueError):
                seal.seal(input,input,hashlib.sha256(b"source").hexdigest())
            with self.assertRaises(ValueError):
                seal.unseal(input,input,hashlib.sha256(b"source").hexdigest())


if __name__=="__main__":
    unittest.main()
