import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import drive_evidence_archive as runner


class FakeDrive:
    def __init__(self, corrupt=False): self.files={}; self.corrupt=corrupt
    def preflight(self, size): return {'availableBytes':10**10}
    def upload(self, path, checksum):
        key=str(len(self.files)); self.files[key]=Path(path).read_bytes(); return key
    def download(self, key, path): Path(path).write_bytes(b'corrupt' if self.corrupt else self.files[key])


class DriveSafety(unittest.TestCase):
    def test_google_transport_preserves_resumable_308_response(self):
        http = runner._archive_http()
        self.assertNotIn(308, http.redirect_codes)
        self.assertEqual(http.timeout, 30)

    def test_restore_download_is_mandatory_for_receipt(self):
        for corrupt in (False, True):
            drive=FakeDrive(corrupt)
            def export(dsn,path, **kwargs):
                Path(path).write_bytes(b'original')
                return {'sha256':runner.archive.digest(path),'databaseBytes':600_000_000}
            def verify(path,checksum,dsn, **kwargs):
                if runner.archive.digest(path)!=checksum: raise ValueError('corruption')
                return {'restoreVerified':True,'deletionPermitted':False}
            with tempfile.TemporaryDirectory() as d, patch.object(runner,'verify_restore_isolation',return_value='separate-database-instance'), patch.object(runner.archive,'export',side_effect=export), patch.object(runner.archive,'restore_check',side_effect=verify) as check:
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

    def test_restore_isolation_rejects_same_host_without_connection(self):
        import psycopg
        with patch.object(psycopg,'connect') as connect:
            with self.assertRaises(ValueError):
                runner.verify_restore_isolation('host=source dbname=live','host=source dbname=test')
            connect.assert_not_called()

    def test_restore_alias_rejected_and_separate_instance_accepted(self):
        import psycopg
        for target_address, expected in [('10.0.0.1',False),('10.0.0.2',True)]:
            conns=[]
            for address,name in [('10.0.0.1','live'),(target_address,'test')]:
                conn=MagicMock();conn.__enter__.return_value=conn
                conn.execute.return_value.fetchone.return_value=(address,5432,name,False)
                conns.append(conn)
            with patch.object(psycopg,'connect',side_effect=conns):
                if expected:
                    self.assertEqual(runner.verify_restore_isolation('host=source','host=target'),'separate-database-instance')
                else:
                    with self.assertRaises(ValueError):runner.verify_restore_isolation('host=source','host=alias')
            for conn in conns:
                conn.execute.assert_any_call('SET TRANSACTION READ ONLY')

    def test_isolation_failure_prevents_export(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner,'verify_restore_isolation',side_effect=ValueError('isolation')), patch.object(runner.archive,'export') as export:
            with self.assertRaisesRegex(ValueError,'isolation'):runner.run('source','restore',d,FakeDrive())
            export.assert_not_called()

    def test_quota_failure_prevents_export(self):
        drive=FakeDrive()
        with tempfile.TemporaryDirectory() as d, patch.object(drive,'preflight',side_effect=ValueError('quota')), patch.object(runner.archive,'export') as export:
            with self.assertRaisesRegex(ValueError,'quota'): runner.run('source','restore',d,drive)
            export.assert_not_called()


if __name__ == '__main__': unittest.main()
