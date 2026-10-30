import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import drive_evidence_archive as runner


class FakeDrive:
    def __init__(self, corrupt=False): self.files={}; self.corrupt=corrupt
    def preflight(self, size): return {'availableBytes':10**10}
    def upload(self, path, checksum):
        key=str(len(self.files)); self.files[key]=Path(path).read_bytes(); return key
    def download(self, key, path): Path(path).write_bytes(b'corrupt' if self.corrupt else self.files[key])


class DriveSafety(unittest.TestCase):
    def test_restore_download_is_mandatory_for_receipt(self):
        for corrupt in (False, True):
            drive=FakeDrive(corrupt)
            def export(dsn,path):
                Path(path).write_bytes(b'original')
                return {'sha256':runner.archive.digest(path),'databaseBytes':600_000_000}
            def verify(path,checksum,dsn, **kwargs):
                if runner.archive.digest(path)!=checksum: raise ValueError('corruption')
                return {'restoreVerified':True,'deletionPermitted':False}
            with tempfile.TemporaryDirectory() as d, patch.object(runner.archive,'export',side_effect=export), patch.object(runner.archive,'restore_check',side_effect=verify) as check:
                if corrupt:
                    with self.assertRaisesRegex(ValueError,'corruption'): runner.run('source','restore',d,drive)
                    self.assertEqual(len(drive.files),1)
                else:
                    receipt=runner.run('source','restore',d,drive)
                    self.assertTrue(receipt['remoteDownloadVerified'])
                    self.assertEqual(receipt['storageState'],'caution')
                    self.assertEqual(len(drive.files),2)
                    self.assertFalse(json.loads(drive.files['1'])['deletionPermitted'])
                self.assertEqual(check.call_count,2)

    def test_quota_failure_prevents_export(self):
        drive=FakeDrive()
        with tempfile.TemporaryDirectory() as d, patch.object(drive,'preflight',side_effect=ValueError('quota')), patch.object(runner.archive,'export') as export:
            with self.assertRaisesRegex(ValueError,'quota'): runner.run('source','restore',d,drive)
            export.assert_not_called()


if __name__ == '__main__': unittest.main()
