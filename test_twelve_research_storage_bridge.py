"""No real Twelve Data API, account secrets or Drive uploads in tests."""
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import twelve_research_storage_bridge as bridge


class FakeDrive:
    def __init__(self, corrupt=False):
        self.corrupt = corrupt
        self.calls = []
        self.objects = []
    def preflight(self, count):
        self.calls.append('preflight')
        if count < 100 or count > 1024 * 1024:
            raise ValueError('unexpected size')
        return {'availableBytes': 1000000000}
    def upload(self, path, checksum):
        self.calls.append('upload')
        body = Path(path).read_bytes()
        self.objects.append(body)
        self.checksum = checksum
        return 'synthetic-fake-file'
    def download(self, file_id, destination, max_bytes=None):
        self.calls.append('download')
        assert file_id == 'synthetic-fake-file'
        assert max_bytes == 1024 * 1024
        data = bytearray(self.objects[-1])
        if self.corrupt:
            data[-1] ^= 1
        Path(destination).write_bytes(data)


ENV = {
    'BOB_TWELVE_DRIVE_SYNTHETIC_TEST':'1',
    'BOB_TWELVE_RESEARCH_DRIVE_FOLDER_ID':'research-app-owned-folder',
    'BOB_TWELVE_RESEARCH_PRIVATE_PARENT_ID':'private-parent-folder',
    'BOB_ARCHIVE_DRIVE_FOLDER_ID':'existing-evidence-folder',
    'PUSH_SERVICE_TOKEN':'a-test-only-nonsecret-encryption-root-'+'z'*48,
}


class TwelveResearchStorageBridgeTests(unittest.TestCase):
    def test_manual_scope_default_off_and_archive_folder_not_reused(self):
        self.assertEqual(bridge.drive_scope({})['code'],
                         'MANUAL_TEST_NOT_AUTHORIZED')
        self.assertEqual(bridge.drive_scope({**ENV,
            'BOB_TWELVE_RESEARCH_DRIVE_FOLDER_ID':
            ENV['BOB_ARCHIVE_DRIVE_FOLDER_ID']})['code'],
            'DEDICATED_PRIVATE_FOLDER_REQUIRED')

    def test_aiven_observation_never_grants_research_writes(self):
        healthy = lambda: {'status':'observed','findings':[],
                           'clientConnections':1,'hostMemoryAvailablePercent':None}
        result = bridge.aiven_readiness(healthy)
        self.assertEqual(result['code'],'AIVEN_READ_ONLY_OBSERVED')
        self.assertFalse(result['writesEnabled'])
        self.assertFalse(result['hostRamVerified'])
        self.assertFalse(result['readyForQuotaLedger'])
        self.assertEqual(bridge.aiven_readiness(
            lambda: {'status':'observed','findings':['connection-pressure'],
                     'clientConnections':17})['code'], 'AIVEN_BUSY')
        self.assertEqual(bridge.aiven_readiness(
            lambda: {'status':'not-configured'})['code'], 'AIVEN_UNVERIFIED')

    def test_encrypted_cloud_roundtrip_uses_synthetic_only(self):
        drive = FakeDrive()
        with patch.dict(os.environ, ENV, clear=True):
            r = bridge.run_manual(drive=drive,inspect=lambda: {
                'status':'observed','findings':[],'clientConnections':1})
        self.assertEqual(r['drive']['code'], 'SYNTHETIC_DRIVE_ROUNDTRIP_VERIFIED')
        self.assertTrue(r['drive']['encrypted'])
        self.assertFalse(r['drive']['licensedBarsStored'])
        self.assertFalse(r['aiven']['writesEnabled'])
        self.assertEqual(drive.calls, ['preflight','upload','download'])
        self.assertTrue(drive.objects[0].startswith(b'BOBAES01'))
        self.assertNotIn(b'BOB-TWELVE-DRIVE-SYNTHETIC-V1', drive.objects[0])

    def test_remote_corruption_never_issues_success(self):
        drive = FakeDrive(corrupt=True)
        with patch.dict(os.environ, ENV, clear=True):
            result=bridge.synthetic_drive_roundtrip(drive)
        self.assertEqual(result['code'],'REMOTE_CIPHERTEXT_MISMATCH')
        self.assertFalse(result['licensedBarsStored'])

    def test_disabled_run_does_not_open_drive_or_write_data(self):
        drive=FakeDrive()
        with patch.dict(os.environ, {}, clear=True):
            r=bridge.run_manual(drive=drive,inspect=lambda: {'status':'not-configured'})
        self.assertEqual(r['drive']['code'], 'MANUAL_TEST_NOT_AUTHORIZED')
        self.assertEqual(drive.calls, [])


if __name__ == '__main__':
    unittest.main()
