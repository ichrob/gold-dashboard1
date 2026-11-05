import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from storage_pressure import policy, delay, verified_writer_preflight

class PressureTests(unittest.TestCase):
    def test_boundaries(self):
        for size, seconds in [(0,3600),(499999999,3600),(500000000,900),(699999999,900),(700000000,300),(5000000000,300)]:
            self.assertEqual(policy(size)['nextRunSeconds'],seconds)
    def test_unknown_and_failures_back_off(self):
        for size in (None,True,-1,'700000000'):
            self.assertEqual(policy(size)['state'],'unknown')
        self.assertEqual(delay({'status':'deferred','pressure':policy(4500000000)}),3600)
        self.assertEqual(delay({'status':'archive-running'}),60)
        self.assertEqual(delay({'status':'checked','pressure':policy(4500000000)}),300)

    def test_upgraded_volume_does_not_slow_existing_offload(self):
        from storage_capacity import ALLOCATION_BYTES, MAX_VOLUME_BYTES
        self.assertEqual(ALLOCATION_BYTES, 5_000_000_000)
        self.assertGreater(MAX_VOLUME_BYTES, 700_000_000)
        self.assertEqual(policy(652_850_879)['nextRunSeconds'], 900)
        self.assertEqual(policy(763_000_000)['nextRunSeconds'], 300)
        # A failed cycle must back off even above the operating target.
        self.assertEqual(delay({'status': 'failed', 'pressure': policy(763_000_000)}), 3600)


class OffloadEvidenceGuardTests(unittest.TestCase):
    NOW = 1_800_000_000

    @classmethod
    def proof(cls):
        return {'latestVerifiedAttempt':{
            'status':'verified', 'updatedAt':datetime.fromtimestamp(cls.NOW,timezone.utc).isoformat(),
            'restoreVerified':True,'remoteDownloadVerified':True,'evidenceDeleted':False,
            'encryptionVerified':True,'encryptionVersion':'aes-256-gcm-stream-v1',
            'recoveryKeyVerified':True,'restoreIsolation':'separate-database-instance',
            'scope':'reviewed-evidence-tables-not-full-database-backup'}}

    def test_recovery_proof_and_fresh_volume_required(self):
        from storage_capacity import MAX_VOLUME_BYTES
        from render_disk_metrics import RESOURCE
        volume={'status':'observed','resource':RESOURCE,'unit':'bytes',
                'observedAt':self.NOW-20,'diskUsage':MAX_VOLUME_BYTES-10}
        with patch('storage_budget.archive_status',return_value=self.proof()) as proof, \
             patch('render_disk_metrics.report',return_value=volume) as measured:
            self.assertIsNone(verified_writer_preflight(object(),now=self.NOW))
            proof.assert_called_once();measured.assert_called_once()
        invalid=self.proof();invalid['latestVerifiedAttempt']['recoveryKeyVerified']=False
        with patch('storage_budget.archive_status',return_value=invalid), \
             patch('render_disk_metrics.report') as measured:
            self.assertEqual(verified_writer_preflight(object(),now=self.NOW)['status'],
                             'backup-proof-not-fresh')
            measured.assert_not_called()
        for change in ({'observedAt':self.NOW-301},
                       {'diskUsage':MAX_VOLUME_BYTES+1},
                       {'unit':'GB'},{'resource':'wrong'}):
            with self.subTest(change=change), \
                 patch('storage_budget.archive_status',return_value=self.proof()), \
                 patch('render_disk_metrics.report',return_value={**volume,**change}):
                self.assertEqual(verified_writer_preflight(object(),now=self.NOW)['status'],
                                 'fresh-volume-proof-unavailable')

    def test_all_automatic_writers_exit_before_sql_without_evidence(self):
        import cold_analysis, cold_metrics, cold_observations
        class Connection:
            autocommit=True
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def execute(self,*args,**kwargs):
                raise AssertionError('No SQL should run without required proof')
        with patch('storage_pressure.verified_writer_preflight',
                   return_value={'status':'backup-proof-not-fresh','movedRows':0}):
            for module in (cold_analysis,cold_metrics,cold_observations):
                with self.subTest(module=module.__name__):
                    self.assertEqual(module.run_once(factory=Connection)['status'],
                                     'backup-proof-not-fresh')
