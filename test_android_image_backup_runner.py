"""Manual private PNG remote backup: synthetic transport and isolated PG tests.

Test mocks do NOT establish a real remote/independent production backup.
"""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import android_image_backup_runner as runner
import android_image_backup_prepare as prep
from test_android_image_recovery_bundle import BundleUnitTests


class DummyConnection:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class MemoryDrive:
    def __init__(self,corrupt=False):
        self.cipher=None
        self.corrupt=corrupt
        self.uploads=0
    def preflight(self, n):
        self.required=n
        return {'availableBytes': 2000000000, 'reserveBytes':268435456}
    def upload(self,path,digest):
        self.cipher=Path(path).read_bytes()
        if hashlib.sha256(self.cipher).hexdigest()!=digest:
            raise AssertionError('Ciphertext upload checksum invalid')
        self.uploads+=1
        return 'A'*24
    def download(self,file_id,destination,max_bytes=None):
        assert file_id=='A'*24
        data=self.cipher
        if self.corrupt:
            data=data[:-1]+bytes([data[-1]^1])
        assert len(data)<=max_bytes
        with open(destination,'xb') as file:
            file.write(data)


class ManualRunnerTests(unittest.TestCase):
    def bundle(self):
        helper=BundleUnitTests()
        return helper.make_bundle(helper.manifest())

    def test_readonly_source_and_encrypted_remote_roundtrip(self):
        blob,digest=self.bundle()
        drive=MemoryDrive()
        args=[]
        def fake_connect(*values,**kw):
            args.append(kw)
            return DummyConnection()
        with tempfile.TemporaryDirectory() as work:
            with patch('psycopg.connect',side_effect=fake_connect), \
                 patch.object(runner,'verify_restore_isolation',
                              return_value='separate-database-instance') as isolated, \
                 patch.object(prep,'pack_active_source_readonly',
                              return_value=(blob,digest)) as read, \
                 patch.object(runner,'_restore_once',return_value=1) as restored:
                result=runner.run_once('source-dsn','restore-dsn',drive,b'S'*32,
                                       '1'*32,'a'*64,work_directory=str(Path(work)/'private'))
        isolated.assert_called_once_with('source-dsn','restore-dsn')
        self.assertEqual(read.call_count,2)
        restored.assert_called_once()
        self.assertEqual(restored.call_args.args[1:],(blob,digest))
        self.assertTrue(all('default_transaction_read_only=on' in a['options'] for a in args))
        self.assertEqual(drive.uploads,1)
        self.assertNotIn(b'private trading app text',drive.cipher)
        self.assertTrue(result['remoteDownloadVerified'])
        self.assertTrue(result['sourcePreserved'])
        self.assertFalse(result['deletionAuthorized'])
        self.assertFalse(result['imageMigrationAuthorized'])
        self.assertIsNone(result['diskBytesFreed'])

    def test_wrong_independent_server_fails_before_source_or_drive(self):
        drive=MemoryDrive()
        with patch.object(runner,'verify_restore_isolation',
                          side_effect=ValueError('same server')), \
             patch.object(prep,'pack_active_source_readonly') as source:
            with self.assertRaises(ValueError):
                runner.run_once('source','source',drive,b'S'*32,'1'*32,'a'*64)
        source.assert_not_called()
        self.assertEqual(drive.uploads,0)

    def test_corrupted_remote_rejected_before_any_restore_or_receipt(self):
        blob,digest=self.bundle()
        drive=MemoryDrive(corrupt=True)
        with tempfile.TemporaryDirectory() as work:
            with patch.object(runner,'verify_restore_isolation',
                              return_value='separate-database-instance'), \
                 patch('psycopg.connect',return_value=DummyConnection()), \
                 patch.object(prep,'pack_active_source_readonly',
                              return_value=(blob,digest)), \
                 patch.object(runner,'_restore_once') as restore:
                with self.assertRaisesRegex(ValueError,'Remote encrypted image mismatch'):
                    runner.run_once('source','target',drive,b'S'*32,'1'*32,'a'*64,
                                    work_directory=str(Path(work)/'private'))
        restore.assert_not_called()
        self.assertEqual(drive.uploads,1)

    def test_changed_source_metadata_fails_closed_after_restore(self):
        blob,digest=self.bundle()
        drive=MemoryDrive()
        with tempfile.TemporaryDirectory() as work:
            with patch.object(runner,'verify_restore_isolation',
                              return_value='separate-database-instance'), \
                 patch('psycopg.connect',return_value=DummyConnection()), \
                 patch.object(prep,'pack_active_source_readonly',
                              side_effect=[(blob,digest),(blob,'0'*64)]), \
                 patch.object(runner,'_restore_once',return_value=1):
                with self.assertRaisesRegex(ValueError,'Original image record changed'):
                    runner.run_once('source','target',drive,b'S'*32,'1'*32,'a'*64,
                                    work_directory=str(Path(work)/'private'))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI integration only')
class IsolatedRestoreTests(unittest.TestCase):
    def test_temporary_schema_original_reference_objects_restored_and_rolled_back(self):
        import psycopg
        from test_android_image_recovery_bundle import BundleUnitTests
        blob,digest=BundleUnitTests().make_bundle(BundleUnitTests().manifest())
        # This tests transactional roundtrip only: NOT a different server.
        # Real server-isolation gate remains mandatory in the manual runner.
        count=runner._restore_once(os.environ['BOB_TEST_DATABASE_URL'],blob,digest)
        self.assertEqual(count,1)


if __name__=='__main__':
    unittest.main()
