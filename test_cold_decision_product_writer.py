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

    def test_readonly_live_preview_counts_duplicate_old_lists_without_mutation(self):
        first=self.put('old-1',22,self.sample)
        second=self.put('old-2',21,self.sample)
        recent=self.put('new',1,self.sample)
        self.put('empty',20,[])
        when=datetime.fromtimestamp(self.now,tz=timezone.utc).isoformat()
        proof={'latestPersistedAttempt':{
            'status':'verified','restoreVerified':True,'remoteDownloadVerified':True,
            'updatedAt':when,'evidenceDeleted':False}}
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'0'}):
            with self.conn.transaction():
                self.conn.execute('SET TRANSACTION READ ONLY')
                plan=writer.preview(self.conn,now=self.now,archive_proof=proof)
        self.assertEqual(plan['status'],'sampled')
        self.assertTrue(plan['readOnly'])
        self.assertEqual(plan['scannedRows'],3)
        self.assertEqual(plan['eligibleRows'],2)
        self.assertEqual(plan['distinctProductArrays'],1)
        self.assertEqual(plan['sharedArrayRows'],1)
        self.assertEqual(plan['backupProofState'],'verified-fresh')
        self.assertEqual(plan['sourceChanges'],0)
        self.assertEqual(plan['uploadedFiles'],0)
        self.assertFalse(plan['manualRunAuthorized'])
        self.assertIsNone(plan['diskBytesFreed'])
        import json
        summary=json.dumps(plan)
        self.assertNotIn('SAMPLE0',summary)
        self.assertNotIn('9007199254740993',summary)
        self.assertEqual(self.conn.execute(
            'SELECT payload FROM bob_decision_audit WHERE id=%s',('old-1',)).fetchone()[0],first)
        self.assertEqual(self.conn.execute(
            'SELECT payload FROM bob_decision_audit WHERE id=%s',('old-2',)).fetchone()[0],second)
        self.assertEqual(self.conn.execute(
            'SELECT payload FROM bob_decision_audit WHERE id=%s',('new',)).fetchone()[0],recent)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_cold_decision_product_refs').fetchone()[0],0)

    def test_preview_stale_backup_does_not_claim_permission(self):
        self.put('old-1',22,self.sample)
        result=writer.preview(self.conn,now=self.now,archive_proof={
            'latestPersistedAttempt':{
                'status':'verified','restoreVerified':True,
                'remoteDownloadVerified':True,
                'updatedAt':datetime.fromtimestamp(self.now-86400,tz=timezone.utc).isoformat()}})
        self.assertEqual(result['status'],'sampled')
        self.assertEqual(result['backupProofState'],'verified-but-stale')
        self.assertFalse(result['manualRunAuthorized'])

    def test_one_row_pilot_does_not_skip_other_old_decisions(self):
        first=self.put('old-1',22,self.sample)
        second=self.put('old-2',21,self.sample)
        fake=FakePrivateDrive()
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
            result=writer.offload_batch(self.conn,fake,approval=self.approval,
                                        now=self.now,max_updates=1)
        self.assertEqual(result['status'],'verified-offload')
        self.assertEqual(result['movedRows'],1)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_cold_decision_product_refs').fetchone()[0],1)
        row1=self.conn.execute(
            "SELECT payload FROM bob_decision_audit WHERE id='old-1'").fetchone()[0]
        row2=self.conn.execute(
            "SELECT payload FROM bob_decision_audit WHERE id='old-2'").fetchone()[0]
        self.assertNotIn('products',row1)
        self.assertEqual(row2,second)
        with self.conn.transaction():
            self.conn.execute('SET TRANSACTION READ ONLY')
            recovered=reader.resolve(self.conn,'old-1',row1,drive=fake)
        self.assertEqual(codec.encoded(recovered),codec.encoded(first))
        # Running another explicit, separately approved test may process the
        # next row; a single invocation can never update two originals.
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}):
            again=writer.offload_batch(self.conn,fake,approval=self.approval,
                                       now=self.now,max_updates=1)
        self.assertEqual(again['movedRows'],1)
        self.assertEqual(again['newUniqueObjects'],0)
        self.assertEqual(len(fake.files),1)

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

class RetainedArchiveProofTests(unittest.TestCase):
    def test_interrupted_latest_attempt_uses_last_verified_but_checks_age(self):
        from datetime import datetime, timezone
        now=100000
        proof={'latestPersistedAttempt':{
            'status':'running',
            'updatedAt':datetime.fromtimestamp(now-60,timezone.utc).isoformat(),
            'restoreVerified':False,'remoteDownloadVerified':False},
            'latestVerifiedAttempt':{
            'status':'verified',
            'updatedAt':datetime.fromtimestamp(now-86400,timezone.utc).isoformat(),
            'restoreVerified':True,'remoteDownloadVerified':True,
            'evidenceDeleted':False}}
        self.assertEqual(writer._proof_state(proof,now),'verified-but-stale')
        proof['latestVerifiedAttempt']['updatedAt']=datetime.fromtimestamp(
            now-1800,timezone.utc).isoformat()
        self.assertEqual(writer._proof_state(proof,now),'verified-fresh')
        proof['latestVerifiedAttempt']['restoreVerified']=False
        self.assertEqual(writer._proof_state(proof,now),'no-verified-restore')


class IndependentProductionGates(unittest.TestCase):
    def test_stale_persisted_restore_stops_before_init_or_disk_lookup(self):
        from unittest.mock import MagicMock
        now=100000
        conn=MagicMock()
        conn.__enter__.return_value=conn
        factory=Mock(return_value=conn)
        old=datetime.fromtimestamp(now-86400,tz=timezone.utc).isoformat()
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}), \
             patch('storage_budget.archive_status',return_value={
                 'latestPersistedAttempt':{'status':'verified','updatedAt':old,
                     'restoreVerified':True,'remoteDownloadVerified':True}}), \
             patch('render_disk_metrics.report') as volume, \
             patch.object(writer,'init') as init:
            result=writer.run_once(factory=factory,now=now,approval={
                'restoreVerified':True,'remoteDownloadVerified':True,'observedAt':now})
        self.assertEqual(result['status'],'backup-proof-not-fresh')
        volume.assert_not_called()
        init.assert_not_called()
        conn.execute.assert_not_called()

    def test_fresh_restore_without_recent_disk_is_not_authorized(self):
        from unittest.mock import MagicMock
        now=100000
        conn=MagicMock()
        conn.__enter__.return_value=conn
        proof={'latestPersistedAttempt':{
            'status':'verified','updatedAt':datetime.fromtimestamp(
                now,tz=timezone.utc).isoformat(),
            'restoreVerified':True,'remoteDownloadVerified':True}}
        with patch.dict(os.environ,{'BOB_COLD_DECISION_PRODUCTS_ENABLED':'1'}), \
             patch('storage_budget.archive_status',return_value=proof), \
             patch('render_disk_metrics.report',return_value={
                 'status':'observed','resource':'dpg-datjno1srm7s738vv500-a',
                 'unit':'bytes','observedAt':now-900,'diskUsage':690000000}), \
             patch.object(writer,'init') as init:
            result=writer.run_once(factory=lambda:conn,now=now,approval={
                'restoreVerified':True,'remoteDownloadVerified':True,'observedAt':now})
        self.assertEqual(result['status'],'fresh-volume-proof-unavailable')
        init.assert_not_called()
        conn.execute.assert_not_called()
