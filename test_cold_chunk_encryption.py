import gzip
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cold_metrics as codec
import cold_chunk_encryption as encryption
from test_cold_decision_product_writer import FakePrivateDrive as FakeDrive


class EncryptedColdTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ, {'PUSH_SERVICE_TOKEN':'offline-test-root-'*4})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.rows=[['hash','decision-products',0,None,
                    {'products':[{'price':9007199254740993,'name':'Original ä'}]}]]

    def archive(self, raw=None):
        raw=codec.encoded({'format':codec.FORMAT,'rows':self.rows}) if raw is None else raw
        with tempfile.TemporaryDirectory() as tmp:
            source,dest=Path(tmp)/'source.gz',Path(tmp)/'sealed.bin'
            source.write_bytes(gzip.compress(raw,mtime=0))
            checksum=encryption.seal_chunk(source,dest)
            blob=dest.read_bytes()
        drive=FakeDrive()
        drive.files['encrypted']=blob
        return drive,checksum

    def test_exact_remote_readthrough_and_no_plain_gzip_upload(self):
        drive,checksum=self.archive()
        self.assertTrue(drive.files['encrypted'].startswith(encryption.MAGIC))
        self.assertNotIn(b'Original',drive.files['encrypted'])
        self.assertEqual(codec.read_chunk(drive,'encrypted',checksum,cached=False),self.rows)

    def test_wrong_key_and_authenticated_ciphertext_corruption_fail_closed(self):
        drive,checksum=self.archive()
        with patch.dict(os.environ, {'PUSH_SERVICE_TOKEN':'different-root-'*4}):
            with self.assertRaises(codec.ColdArchiveUnavailable):
                codec.read_chunk(drive,'encrypted',checksum,cached=False)
        blob=bytearray(drive.files['encrypted']); blob[-1]^=1
        drive.files['encrypted']=bytes(blob)
        with self.assertRaises(codec.ColdArchiveUnavailable):
            codec.read_chunk(drive,'encrypted',codec.digest(blob),cached=False)

    def test_encrypted_zip_bomb_is_bounded(self):
        drive,checksum=self.archive(b' '*(codec.MAX_RAW+1))
        with self.assertRaises(codec.ColdArchiveUnavailable):
            codec.read_chunk(drive,'encrypted',checksum,cached=False)

    def test_missing_key_prevents_encryption(self):
        with patch.dict(os.environ, {'PUSH_SERVICE_TOKEN':''}):
            with self.assertRaises(ValueError):
                self.archive()

    def test_wrong_external_digest_fails_before_decryption(self):
        drive,_=self.archive()
        with patch('cold_chunk_encryption.open_chunk') as decrypt:
            with self.assertRaises(codec.ColdArchiveUnavailable):
                codec.read_chunk(drive,'encrypted','0'*64,cached=False)
            decrypt.assert_not_called()


if __name__=='__main__':
    unittest.main()
