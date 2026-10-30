import os
import unittest
from unittest.mock import patch
import archive_worker as worker

class DB:
    def __init__(self): self.claimed=False; self.calls=[]
    def __call__(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args=()):
        self.calls.append((sql,args))
        self.new=not self.claimed
        if 'INSERT' in sql:self.claimed=True
        return self
    def fetchone(self): return ('day',) if self.new else None

class WorkerTests(unittest.TestCase):
    def env(self):
        return patch.dict(os.environ, {'BOB_ARCHIVE_ENABLED':'1',
            'DATABASE_URL':'test-only', 'BOB_ARCHIVE_RESTORE_DATABASE_URL':'restore-only', 'BOB_ARCHIVE_DRIVE_FOLDER_ID':'test-only',
            'BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON':'test-only'})

    def test_disabled_does_not_access_database(self):
        with patch.dict(os.environ, {'BOB_ARCHIVE_ENABLED':'0'}):
            db=DB(); worker.cycle(db)
            self.assertFalse(db.calls)

    def test_missing_restore_server_blocks_before_claim(self):
        with self.env(), patch.dict(os.environ, {'BOB_ARCHIVE_RESTORE_DATABASE_URL':''}):
            db=DB()
            self.assertEqual(worker.cycle(db)['status'],'blocked')
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

    def test_only_remote_restore_receipt_can_succeed(self):
        with self.env():
            for receipt, expected in [({'restoreVerified':True},'failed'),
                ({'restoreVerified':True,'remoteDownloadVerified':True,
                  'deletionPermitted':False,'receiptFileId':'test'},'verified')]:
                self.assertEqual(worker.cycle(DB(),lambda:receipt)['status'],expected)

if __name__=='__main__':unittest.main()
