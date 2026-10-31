"""Offline and PostgreSQL regressions for the disabled-by-default cold writer."""
import os
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import cold_metrics as codec
import cold_decision_products as reader
import cold_decision_product_writer as writer


class FakePrivateDrive:
    def __init__(self):
        self.files={}
        self.corrupt=False
        self.after_upload=None

    def upload(self,path,checksum):
        blob=Path(path).read_bytes()
        if codec.digest(blob)!=checksum:
            raise ValueError('Invalid upload original')
        file_id='testfile'+str(len(self.files)+1)
        self.files[file_id]=blob
        if self.after_upload:
            self.after_upload()
        return file_id

    def download(self,file_id,path,max_bytes=None):
        blob=self.files[file_id]
        if self.corrupt:
            blob=blob[:-2]+b'XX'
        if max_bytes is not None and len(blob)>max_bytes:
            raise ValueError('File too big')
        Path(path).write_bytes(blob)


class WriterGuardTests(unittest.TestCase):
    def test_manual_writer_stays_disabled_by_default_without_database_or_drive(self):
        factory=Mock()
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'0'}):
            self.assertEqual(writer.run_once(factory=factory,approval={
                'restoreVerified':True,'remoteDownloadVerified':True,'observedAt':1000},now=1000),
                {'status':'disabled','movedRows':0})
        factory.assert_not_called()

    def test_restore_and_remote_proof_and_recency_required(self):
        conn=Mock(autocommit=True)
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
            for approval in (None,{}, {'restoreVerified':True},
                {'restoreVerified':True,'remoteDownloadVerified':True,'observedAt':0},
                {'restoreVerified':True,'remoteDownloadVerified':False,'observedAt':100}):
                self.assertEqual(writer.offload_batch(conn,Mock(),approval=approval,now=1001)['status'],'disabled')
        conn.execute.assert_not_called()


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class WriterPGTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        import uuid
        self.conn=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True)
        self.schema='decision_cold_'+uuid.uuid4().hex
        self.conn.execute('CREATE SCHEMA '+self.schema)
        self.conn.execute('SET search_path TO '+self.schema)
        self.conn.execute('''CREATE TABLE bob_decision_audit
            (id text primary key, recorded_at timestamptz not null,payload jsonb not null)''')
        self.conn.execute('CREATE INDEX decision_time ON bob_decision_audit(recorded_at,id)')
        writer.init(self.conn)
        self.now=1780000000.0
        self.approval={'restoreVerified':True,'remoteDownloadVerified':True,'observedAt':self.now}
        self.sample=[{'isin':'SAMPLE'+str(i),'price':9007199254740993,
                      'quoteAt':'2026-05-01T10:00:00Z'} for i in range(10)]

    def tearDown(self):
        self.conn.execute('RESET search_path')
        self.conn.execute('DROP SCHEMA '+self.schema+' CASCADE')
        self.conn.close()

    def put(self,id,age_days,products):
        from psycopg.types.json import Jsonb
        at=datetime.fromtimestamp(self.now,tz=timezone.utc)-timedelta(days=age_days)
        record={'id':id,'direction':'LONG','recordedAt':1780000000000,
                'products':products,'marketEvaluable':True}
        self.conn.execute('INSERT INTO bob_decision_audit VALUES(%s,%s,%s)',
                          (id,at,Jsonb(record)))
        return record

    def test_share_verified_drive_chunk_and_resolve_both_originals(self):
        originals={
            'old-1':self.put('old-1',22,self.sample),
            'old-2':self.put('old-2',21,self.sample),
            'new':self.put('new',1,self.sample),
            'empty':self.put('empty',20,[])
        }
        fake=FakePrivateDrive()
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
            r=writer.offload_batch(self.conn,fake,approval=self.approval,now=self.now)
        self.assertEqual(r['status'],'verified-offload')
        self.assertEqual(r['movedRows'],2)
        self.assertEqual(r['newUniqueObjects'],1)
        self.assertTrue(r['readThroughVerified'])
        self.assertIsNone(r['diskBytesFreed'])
        self.assertEqual(len(fake.files),1)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_cold_decision_product_objects').fetchone()[0],1)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_cold_decision_product_refs').fetchone()[0],2)
        for id, original in originals.items():
            p=self.conn.execute('SELECT payload FROM bob_decision_audit WHERE id=%s',(id,)).fetchone()[0]
            if id.startswith('old'):
                self.assertNotIn('products',p)
                self.assertIn(reader.TAG,p)
                with self.conn.transaction():
                    self.conn.execute('SET TRANSACTION READ ONLY')
                    recovered=reader.resolve(self.conn,id,p,drive=fake)
                self.assertEqual(codec.encoded(recovered),codec.encoded(original))
                self.assertEqual(recovered['products'][0]['price'],9007199254740993)
            else:
                self.assertEqual(p,original)
        self.assertEqual(writer.status(self.conn)['offloadedRows'],2)

    def test_failed_remote_verification_leaves_original_and_no_refs(self):
        original=self.put('old-1',22,self.sample)
        fake=FakePrivateDrive()
        fake.corrupt=True
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
            with self.assertRaises(codec.ColdArchiveUnavailable):
                writer.offload_batch(self.conn,fake,approval=self.approval,now=self.now)
        self.assertEqual(self.conn.execute(
            "SELECT payload FROM bob_decision_audit WHERE id='old-1'").fetchone()[0],original)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bob_cold_decision_product_refs').fetchone()[0],0)

    def test_concurrent_edit_after_upload_is_not_overwritten(self):
        original=self.put('old-1',22,self.sample)
        fake=FakePrivateDrive()
        from psycopg.types.json import Jsonb
        modified={**original,'reason':'concurrent-update'}
        def concurrent_change():
            self.conn.execute("UPDATE bob_decision_audit SET payload=%s WHERE id='old-1'",(Jsonb(modified),))
        fake.after_upload=concurrent_change
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
            result=writer.offload_batch(self.conn,fake,approval=self.approval,now=self.now)
        self.assertEqual(result['movedRows'],0)
        self.assertEqual(self.conn.execute(
            "SELECT payload FROM bob_decision_audit WHERE id='old-1'").fetchone()[0],modified)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM bob_cold_decision_product_refs').fetchone()[0],0)
