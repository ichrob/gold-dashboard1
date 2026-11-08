import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from storage_pressure import policy, delay, verified_writer_preflight

class PressureTests(unittest.TestCase):
    def test_boundaries(self):
        from storage_capacity import CAUTION_BYTES, ACTION_BYTES
        # Logical size alone never authorizes the former 5-/15-min cadence.
        for size in (0, 499999999, 500000000, 699999999, 700000000, 5000000000):
            self.assertEqual(policy(size)['nextRunSeconds'], 3600)
            self.assertEqual(policy(size)['basis'], 'verified-volume-required')
        for volume, seconds in ((0,3600),(CAUTION_BYTES-1,3600),
                                (CAUTION_BYTES,900),(ACTION_BYTES-1,900),
                                (ACTION_BYTES,300)):
            self.assertEqual(policy(758593215, volume)['nextRunSeconds'], seconds)
            self.assertEqual(policy(758593215, volume)['basis'], 'physical-render-volume')

    def test_unknown_and_failures_back_off(self):
        from storage_capacity import ACTION_BYTES
        for size in (None,True,-1,'700000000'):
            self.assertEqual(policy(size)['state'],'unknown')
        self.assertEqual(policy(750000000, True)['nextRunSeconds'], 3600)
        self.assertEqual(delay({'status':'deferred','pressure':policy(4500000000,ACTION_BYTES)}),3600)
        self.assertEqual(delay({'status':'archive-running'}),60)
        self.assertEqual(delay({'status':'checked','pressure':policy(4500000000,ACTION_BYTES)}),300)

    def test_five_gb_low_usage_never_triggers_fast_offload(self):
        from storage_capacity import ALLOCATION_BYTES, CAUTION_BYTES
        self.assertEqual(ALLOCATION_BYTES, 5_000_000_000)
        self.assertEqual(policy(758593215, 869167100)['nextRunSeconds'], 3600)
        self.assertLess(869167100, CAUTION_BYTES)
        self.assertEqual(delay({'status': 'failed', 'pressure': policy(763000000,869167100)}), 3600)


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

    def test_comfortable_volume_does_not_rewrite_old_originals(self):
        from render_disk_metrics import RESOURCE
        from storage_capacity import CAUTION_BYTES
        volume={'status':'observed','resource':RESOURCE,'unit':'bytes',
                'observedAt':self.NOW-20,'diskUsage':CAUTION_BYTES-1}
        with patch('storage_budget.archive_status',return_value=self.proof()), \
             patch('render_disk_metrics.report',return_value=volume):
            self.assertEqual(verified_writer_preflight(object(),now=self.NOW)['status'],
                             'capacity-comfortable-no-offload')

    def test_all_automatic_writers_exit_before_sql_without_evidence(self):
        import cold_analysis, cold_metrics, cold_observations, cold_test_evidence
        class Connection:
            autocommit=True
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def execute(self,*args,**kwargs):
                raise AssertionError('No SQL should run without required proof')
        with patch('storage_pressure.verified_writer_preflight',
                   return_value={'status':'backup-proof-not-fresh','movedRows':0}):
            for module in (cold_analysis,cold_metrics,cold_observations,cold_test_evidence):
                with self.subTest(module=module.__name__):
                    self.assertEqual(module.run_once(factory=Connection)['status'],
                                     'backup-proof-not-fresh')
