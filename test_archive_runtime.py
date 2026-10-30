import json
import os
import unittest
from unittest.mock import Mock, patch
import archive_runtime as r
import drive_evidence_archive as d

class DB:
    def __init__(self): self.state={}
    def __call__(self): return self
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,sql,args=()):
        if sql.startswith('INSERT'): self.state[args[0]]=args[1]
        self.row=(self.state[args[0]],) if sql.startswith('SELECT value') and args[0] in self.state else None
        return self
    def fetchone(self): return self.row

class RuntimeTests(unittest.TestCase):
    def folder(self):
        return dict(id='folder123456789',mimeType='application/vnd.google-apps.folder',shared=False,
            trashed=False,parents=['parent'],capabilities={'canAddChildren':True},appProperties={'bobArchiveFolder':'v1'})
    def test_preparation_reuses_persisted_id_without_export(self):
        db=DB();drive=Mock();files=drive.api.files.return_value
        files.generateIds.return_value.execute.return_value={'ids':['folder123456789']}
        files.get.return_value.execute.return_value=self.folder()
        with patch.object(r,'credentials',return_value={'refresh_token':'never-output'}),patch.object(d,'GoogleDrive',return_value=drive),patch.dict(os.environ,BOB_ARCHIVE_PARENT_FOLDER_ID='parent'):
            for _ in range(2):
                result=r.prepare(db)
                self.assertEqual(result['status'],'prepared');self.assertFalse(result['archiveEnabled'])
            files.generateIds.assert_called_once();files.create.assert_not_called()
            self.assertNotIn('never-output',str(db.state));self.assertNotIn('never-output',str(result))
    def test_create_timeout_preserves_id_for_recovery(self):
        db=DB();drive=Mock();files=drive.api.files.return_value
        files.generateIds.return_value.execute.return_value={'ids':['folder123456789']}
        missing=Exception();missing.resp=Mock(status=404)
        files.get.return_value.execute.side_effect=missing
        files.create.return_value.execute.side_effect=TimeoutError('sensitive')
        with patch.object(r,'credentials',return_value={}),patch.object(d,'GoogleDrive',return_value=drive):
            with self.assertRaises(TimeoutError):r.prepare(db)
            self.assertEqual(json.loads(db.state[r.KEY])['folderId'],'folder123456789')
            files.get.return_value.execute.side_effect=None
            files.get.return_value.execute.return_value=self.folder()
            r.prepare(db);files.generateIds.assert_called_once();files.create.assert_called_once()
    def test_shared_folder_rejected_and_wrong_parent_blocks(self):
        db=DB();db.state[r.KEY]=json.dumps({'folderId':'folder123456789'});drive=Mock()
        with patch.object(r,'credentials',return_value={}),patch.object(d,'GoogleDrive',return_value=drive),patch.dict(os.environ,BOB_ARCHIVE_PARENT_FOLDER_ID='different'):
            drive.api.files.return_value.get.return_value.execute.return_value=self.folder()
            self.assertEqual(r.prepare(db)['status'],'awaiting-folder-placement')
            drive.api.files.return_value.get.return_value.execute.return_value={**self.folder(),'shared':True}
            with self.assertRaises(ValueError):r.prepare(db)
    def test_encrypted_credentials_and_scope_guard(self):
        db=DB()
        info=dict(type='authorized_user',scopes=[r.archive_connection.SCOPE],
            token_uri='https://oauth2.googleapis.com/token',refresh_token='private-test-token')
        with patch.dict(os.environ,PUSH_SERVICE_TOKEN='test-only-key'):
            def encrypt(value):
                db.state[r.archive_connection.KEY]=r.archive_connection.cipher().encrypt(
                    json.dumps({'credentials':value}).encode()).decode()
            encrypt(info)
            self.assertNotIn('private-test-token',str(db.state))
            self.assertEqual(r.credentials(db),info)
            encrypt({**info,'scopes':['https://www.googleapis.com/auth/drive']})
            with self.assertRaises(ValueError):r.credentials(db)
            encrypt({**info,'refresh_token':''})
            with self.assertRaises(ValueError):r.credentials(db)

    def test_client_preflight_rejects_wrong_parent_before_quota(self):
        drive=object.__new__(d.GoogleDrive);drive.api=Mock();drive.folder_id='folder123456789';drive.parent_id='different'
        drive.api.files.return_value.get.return_value.execute.return_value=self.folder()
        with self.assertRaises(ValueError):drive.preflight(0)
        drive.api.about.assert_not_called()

if __name__=='__main__':unittest.main()
