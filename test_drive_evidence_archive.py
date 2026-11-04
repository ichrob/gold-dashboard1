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
    def test_transport_leaves_308_for_resumable_upload_handler(self):
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_info'), patch('googleapiclient.discovery.build') as build:
            runner.GoogleDrive(info={}, folder_id='fixture')
            transport = build.call_args.kwargs['http'].http
            self.assertNotIn(308, transport.redirect_codes)
            self.assertIn(301, transport.redirect_codes)
            self.assertEqual(transport.timeout, 30)

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
                    self.assertEqual(receipt['storageState'],'below-budget-threshold')
                    self.assertEqual(len(drive.files),2)
                    self.assertFalse(json.loads(drive.files['1'])['deletionPermitted'])
                self.assertEqual(check.call_count,2)

    def test_encrypted_remote_upload_is_ciphertext_and_replays_after_decrypt(self):
        drive=FakeDrive()
        original=b"PRIVATE-DIAGNOSIS-RECORD-DO-NOT-UPLOAD"
        def export(dsn,path,**kwargs):
            Path(path).write_bytes(original)
            return {'sha256':runner.archive.digest(path),'databaseBytes':600_000_000}
        def verify(path,checksum,dsn,**kwargs):
            self.assertEqual(Path(path).read_bytes(),original)
            self.assertEqual(runner.archive.digest(path),checksum)
            return {'restoreVerified':True,'deletionPermitted':False,
                    'archiveSha256':checksum,'version':'bob-evidence-archive-v3',
                    'scope':'reviewed-evidence-tables-not-full-database-backup'}
        with tempfile.TemporaryDirectory() as d, \
             patch.dict('os.environ',{'BOB_ARCHIVE_ENCRYPT_BEFORE_UPLOAD':'1',
                       'PUSH_SERVICE_TOKEN':'secure-test-only-'+'v'*48,
                       'BOB_ARCHIVE_RECOVERY_ROOT_TOKEN':'secure-test-only-'+'v'*48,
                       'BOB_ARCHIVE_RECOVERY_PROOF_ONCE':'1'}), \
             patch.object(runner,'verify_restore_isolation',
                          return_value='separate-database-instance'), \
             patch.object(runner.archive,'export',side_effect=export), \
             patch.object(runner.archive,'restore_check',side_effect=verify) as check:
            receipt=runner.run('source','restore',d,drive)
        self.assertEqual(check.call_count,2)
        self.assertTrue(receipt['encryptionVerified'])
        self.assertEqual(receipt['encryptionVersion'],'aes-256-gcm-stream-v1')
        self.assertTrue(receipt['recoveryKeyVerified'])
        self.assertTrue(receipt['remoteDownloadVerified'])
        self.assertNotIn(original,drive.files['0'])
        self.assertTrue(drive.files['0'].startswith(b'BOBAES01'))
        self.assertTrue(drive.files['1'].startswith(b'{'))
        persisted=json.loads(drive.files['1'])
        self.assertTrue(persisted['encryptionVerified'])
        self.assertTrue(persisted['recoveryKeyVerified'])

    def test_encrypted_corrupted_remote_file_never_creates_restore_receipt(self):
        drive=FakeDrive(corrupt=True)
        payload=b"original"
        def export(dsn,path,**kw):
            Path(path).write_bytes(payload)
            return {'sha256':runner.archive.digest(path),'databaseBytes':123}
        def verify(path,checksum,dsn,**kw):
            if runner.archive.digest(path)!=checksum:
                raise ValueError('corrupt local evidence')
            return {'restoreVerified':True,'deletionPermitted':False}
        with tempfile.TemporaryDirectory() as d, \
             patch.dict('os.environ',{'BOB_ARCHIVE_ENCRYPT_BEFORE_UPLOAD':'1',
                       'PUSH_SERVICE_TOKEN':'secure-test-only-'+'v'*48}), \
             patch.object(runner,'verify_restore_isolation',
                          return_value='separate-database-instance'), \
             patch.object(runner.archive,'export',side_effect=export), \
             patch.object(runner.archive,'restore_check',side_effect=verify) as check:
            with self.assertRaises(ValueError):
                runner.run('source','restore',d,drive)
        self.assertEqual(check.call_count,1)
        self.assertEqual(len(drive.files),1)

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
