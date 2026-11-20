import os
import unittest
from unittest.mock import patch
import archive_worker as worker
from test_aiven_readonly_probe import URI as AIVEN_TEST_URI

class DB:
    def __init__(self): self.claimed=False; self.calls=[]; self.lock_ok=True
    def __call__(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args=()):
        self.calls.append((sql,args))
        if 'pg_try_advisory_lock' in sql:
            self.new='lock'
        else:
            self.new=not self.claimed
            if 'INSERT' in sql:self.claimed=True
        return self
    def fetchone(self):
        if self.new=='lock': return (self.lock_ok,)
        return ('day',) if self.new else None

class WorkerTests(unittest.TestCase):
    def env(self):
        return patch.dict(os.environ, {'BOB_ARCHIVE_ENABLED':'1',
            'DATABASE_URL':'test-only', 'BOB_ARCHIVE_RESTORE_DATABASE_URL':AIVEN_TEST_URI, 'BOB_ARCHIVE_DRIVE_FOLDER_ID':'test-only',
            'BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON':'test-only'})

    def test_verified_archive_can_use_only_existing_weekend_one_shot(self):
        valid={'status': 'verified',
               'receipt': {'restoreVerified': True,
                           'remoteDownloadVerified': True}}
        with patch('storage_tail_once.configuration',return_value=None):
            self.assertEqual(worker.post_verified_weekend_reclaim(valid)['status'],
                             'not-configured')
        with patch('storage_tail_once.configuration',
                   return_value={'id':'test','table':'bob_metric_checks',
                                 'confirmed':True}), \
             patch('storage_tail_once._weekend',return_value=True), \
             patch('storage_tail_once.run_once',
                   return_value={'status':'already-claimed',
                                 'privateToken':'SHOULD_NOT_LEAK'}) as tail:
            done=worker.post_verified_weekend_reclaim(valid)
            self.assertEqual(done['status'],'already-claimed')
            self.assertIsNone(done['diskBytesFreed'])
            self.assertNotIn('SHOULD_NOT_LEAK',str(done))
            tail.assert_called_once()
        with patch('storage_tail_once.configuration',
                   return_value={'id':'test','table':'bob_metric_checks',
                                 'confirmed':True}), \
             patch('storage_tail_once._weekend',return_value=True), \
             patch('storage_tail_once.run_once',
                   return_value={'status':'memory-pressure'}) as tail:
            pressured=worker.post_verified_weekend_reclaim(valid)
            self.assertEqual(pressured['status'],'memory-pressure')
            self.assertIsNone(pressured['diskBytesFreed'])
            tail.assert_called_once()
        for bad in ({'status':'failed'}, {'status':'verified'},
                    {'status':'verified','receipt':{'restoreVerified':True}}):
            with patch('storage_tail_once.run_once') as tail:
                result=worker.post_verified_weekend_reclaim(bad)
                self.assertIn(result['status'],
                    ('archive-not-verified','restore-not-verified'))
                tail.assert_not_called()
        with patch('storage_tail_once.configuration',return_value={'id':'test'}), \
             patch('storage_tail_once._weekend',return_value=False), \
             patch('storage_tail_once.run_once') as tail:
            self.assertEqual(worker.post_verified_weekend_reclaim(valid)['status'],
                             'outside-weekend')
            tail.assert_not_called()

    def test_disabled_does_not_access_database(self):
        with patch.dict(os.environ, {'BOB_ARCHIVE_ENABLED':'0'}):
            db=DB(); worker.cycle(db)
            self.assertFalse(db.calls)

    def test_missing_restore_server_blocks_before_claim(self):
        with self.env(), patch.dict(os.environ, {'BOB_ARCHIVE_RESTORE_DATABASE_URL':''}):
            db=DB()
            self.assertEqual(worker.cycle(db)['status'],'blocked')
            self.assertFalse(db.calls)

    def test_expiring_render_restore_target_is_blocked_before_claim(self):
        with self.env(), patch.dict(os.environ, {
            'BOB_ARCHIVE_RESTORE_DATABASE_URL':
                'postgresql://fixture:fixture@restore.render.com:5432/test?sslmode=require'}):
            db = DB()
            result = worker.cycle(db)
            self.assertEqual(result['status'], 'blocked')
            self.assertEqual(result['reason'], 'restore-target-not-aiven')
            self.assertFalse(db.calls)

    def test_failure_is_redacted_and_not_repeated(self):
        with self.env():
            db=DB(); runs=[]
            def fail(): runs.append(1); raise ValueError('secret-token')
            result=worker.cycle(db, fail)
            self.assertEqual(result['status'],'failed')
            self.assertNotIn('secret-token',str(db.calls))
            worker.cycle(db, fail)
            self.assertEqual(len(runs),1)

    def test_result_write_failure_preserves_primary_error(self):
        class BrokenReceiptDB(DB):
            def execute(self, sql, args=()):
                if 'UPDATE' in sql: raise TimeoutError('private-dsn')
                return super().execute(sql,args)
        with self.env():
            def fail(): raise ValueError('private-original')
            result = worker.cycle(BrokenReceiptDB(), fail)
            self.assertEqual(result['errorType'], 'ValueError')
            self.assertEqual(result['receiptPersistenceErrorType'], 'TimeoutError')
            self.assertNotIn('private-', str(result))

    def test_busy_storage_lock_does_not_consume_daily_claim(self):
        with self.env():
            db=DB(); db.lock_ok=False
            result=worker.cycle(db, lambda: {'restoreVerified':True})
            self.assertEqual(result['status'],'busy')
            self.assertFalse(any('INSERT' in sql for sql,_ in db.calls))

    def test_invalid_attempt_never_claims(self):
        with self.env(), patch.dict(os.environ, {'BOB_ARCHIVE_ATTEMPT':'bad value'}):
            db=DB()
            self.assertEqual(worker.cycle(db)['status'], 'blocked')
            self.assertFalse(db.calls)

    def test_explicit_attempt_in_claim_and_result_key(self):
        with self.env(), patch.dict(os.environ, {'BOB_ARCHIVE_ATTEMPT':'repair-a'}):
            db=DB(); worker.cycle(db, lambda: {})
            for sql, args in db.calls:
                if 'INSERT' in sql or 'UPDATE' in sql:
                    self.assertEqual(args[-1], 'repair-a')

    def test_encryption_required_when_private_ciphertext_mode_is_enabled(self):
        valid={'restoreVerified':True,'remoteDownloadVerified':True,
               'deletionPermitted':False,'receiptFileId':'verified-test'}
        with self.env(), patch.dict(os.environ,
             {'BOB_ARCHIVE_ENCRYPT_BEFORE_UPLOAD':'1'}):
            self.assertEqual(worker.cycle(DB(),lambda:valid)['status'],'failed')
            self.assertEqual(worker.cycle(DB(),lambda:{**valid,
                'encryptionVerified':True,
                'encryptionVersion':'none'})['status'],'failed')
            self.assertEqual(worker.cycle(DB(),lambda:{**valid,
                'encryptionVerified':True,
                'encryptionVersion':'aes-256-gcm-stream-v1'})['status'],'verified')

    def test_only_remote_restore_receipt_can_succeed(self):
        with self.env():
            for receipt, expected in [({'restoreVerified':True},'failed'),
                ({'restoreVerified':True,'remoteDownloadVerified':True,
                  'deletionPermitted':False,'receiptFileId':'test'},'verified')]:
                self.assertEqual(worker.cycle(DB(),lambda:receipt)['status'],expected)

if __name__=='__main__':unittest.main()
