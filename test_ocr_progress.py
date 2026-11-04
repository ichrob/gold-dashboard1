import copy
import json
import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import handset_list_worker as worker


def rows(numbers):
    from product_quotes import valid_isin
    values=[]
    for number in numbers:
        stem='DE000ZZ'+str(number).zfill(4)
        identifier=next(stem+str(n) for n in range(10) if valid_isin(stem+str(n)))
        values.append('SG Gold Turbo BEST Open-End Call BAR 4000 BP 4000 Bv 10 | '+
                      identifier+' Societe Generale OTC EUR')
    return '\n'.join(values)


class ProgressTests(unittest.TestCase):
    def test_resume_reuses_only_verified_image_before_memory_deferral(self):
        import evaluator_runtime
        actual=evaluator_runtime.run
        first=rows(range(1,6));second=rows(range(6,11))
        saved=[];native=[]
        def execute(args,**kwargs):
            if '--ocr' not in args:return actual(args,**kwargs)
            image=json.loads(kwargs['input'])[0]['png'];native.append(image)
            if image=='second' and len(native)==2:raise worker.OcrMemoryDeferred()
            return SimpleNamespace(stdout=json.dumps([[first if image=='first' else second]*3]))
        payload={'images':[{'png':'first'},{'png':'second'}]}
        with patch.object(evaluator_runtime,'run',side_effect=execute):
            with self.assertRaises(worker.OcrMemoryDeferred):
                worker.process(payload,'2026-11-04T08:00:00Z',save_progress=lambda x:saved.append(copy.deepcopy(x)))
            self.assertEqual(len(saved),1)
            self.assertEqual(set(saved[0]),{'0'})
            result=worker.process(payload,'2026-11-04T08:00:00Z',progress=saved[0],
                                  save_progress=lambda x:saved.append(copy.deepcopy(x)))
        self.assertEqual(native,['first','second','second'])
        self.assertEqual(len(result['items']),10)
        self.assertEqual(len(saved[-1]),2)

    def test_changed_original_or_mode_never_reuses_checkpoint(self):
        image={'png':'original','at':'2026-11-04T08:00:00Z'}
        key=worker.image_work_key(image,False)
        for changed,mode in [({**image,'png':'changed'},False),
                             ({**image,'at':'2026-11-04T08:01:00Z'},False),(image,True)]:
            self.assertNotEqual(key,worker.image_work_key(changed,mode))
        with patch.object(worker,'OCR_PROGRESS_REVISION','new-parser-revision'):
            self.assertNotEqual(key,worker.image_work_key(image,False))

    def test_checkpoint_has_product_rows_only_and_preserves_two_real_reads(self):
        row=rows([1])
        value=worker.sanitize_native_passes(['Portfolio 123\n'+row+'\nKontostand 999',row])
        self.assertEqual(value,[row,row])
        for invalid in ([row],['invalid','invalid'],['x'*30001,row],None):
            self.assertIsNone(worker.sanitize_native_passes(invalid))

    def test_corrupt_or_single_read_checkpoint_cannot_skip_native_work(self):
        import evaluator_runtime
        actual=evaluator_runtime.run
        image={'png':'one'}
        calls=[]
        def execute(args,**kwargs):
            if '--ocr' not in args:return actual(args,**kwargs)
            calls.append(1)
            raise worker.OcrMemoryDeferred()
        progress={'0':{'key':worker.image_work_key(image,False),'passes':[rows([1])]}}
        with patch.object(evaluator_runtime,'run',side_effect=execute):
            with self.assertRaises(worker.OcrMemoryDeferred):
                worker.process({'images':[image]},'2026-11-04T08:00:00Z',progress=progress)
        self.assertEqual(calls,[1])

    def test_exact_uniform_border_removal_preserves_faint_pixels_and_context(self):
        from PIL import Image
        with Image.new('RGB',(1000,512),'white') as image:
            image.putpixel((100,150),(254,254,254))
            image.putpixel((800,450),(0,0,0))
            self.assertEqual(worker.content_bounds(image),(92,142,809,459))
            with image.crop(worker.content_bounds(image)) as crop:
                self.assertEqual(crop.getpixel((8,8)),(254,254,254))
        with Image.new('RGB',(1000,512),'white') as image:
            self.assertEqual(worker.content_bounds(image),(0,0,1000,512))


class ProgressDatabaseTests(unittest.TestCase):
    def test_progress_is_scoped_to_current_owned_reading_batch_and_bounded(self):
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('CI PostgreSQL not configured')
        import psycopg
        import uuid
        from contextlib import contextmanager
        import android_list
        schema='ocr_progress_'+uuid.uuid4().hex
        with psycopg.connect(url) as conn:conn.execute('CREATE SCHEMA '+schema)
        @contextmanager
        def connect():
            with psycopg.connect(url) as conn:
                conn.execute('SET search_path TO '+schema)
                yield conn
        try:
            with connect() as conn:
                conn.execute('CREATE TABLE bob_android_diagnostic_devices(token_hash TEXT PRIMARY KEY,revoked BOOLEAN,expires_at TIMESTAMPTZ)')
                android_list.init(conn)
                conn.execute("INSERT INTO bob_android_diagnostic_devices VALUES('owner',false,now()+interval '1 hour')")
                conn.execute("INSERT INTO bob_android_list_images(batch_id,token_hash,payload,import_receipt) VALUES('batch','owner','{}','{\"stage\":\"reading\"}')")
            progress={'0':{'key':'a'*64,'passes':[rows([1]),rows([1])]}}
            worker.persist_progress(connect,'batch',progress)
            with connect() as conn:
                self.assertEqual(conn.execute("SELECT ocr_progress FROM bob_android_list_images WHERE batch_id='batch'").fetchone()[0],progress)
                conn.execute("UPDATE bob_android_diagnostic_devices SET revoked=true")
            worker.persist_progress(connect,'batch',{})
            with connect() as conn:
                self.assertEqual(conn.execute("SELECT ocr_progress FROM bob_android_list_images WHERE batch_id='batch'").fetchone()[0],progress)
                conn.execute("UPDATE bob_android_diagnostic_devices SET revoked=false")
                conn.execute("UPDATE bob_android_list_images SET import_receipt='{\"stage\":\"synced\"}'")
            worker.persist_progress(connect,'batch',{})
            with connect() as conn:
                self.assertEqual(conn.execute("SELECT ocr_progress FROM bob_android_list_images WHERE batch_id='batch'").fetchone()[0],progress)
                conn.execute("UPDATE bob_android_list_images SET import_receipt='{\"stage\":\"reading\"}',processing_attempts=0,processing_at=NULL,payload=%s::jsonb",(json.dumps({'images':[{'at':'2026-11-04T08:00:00Z'}]}),))
            def fail_verification(*_):raise worker.ListVerificationError('Incomplete list')
            self.assertTrue(worker.tick(connect,fail_verification))
            with connect() as conn:
                self.assertIsNone(conn.execute("SELECT ocr_progress FROM bob_android_list_images WHERE batch_id='batch'").fetchone()[0])
            with self.assertRaises(ValueError):worker.persist_progress(connect,'batch',{'oversized':'x'*120001})
        finally:
            with psycopg.connect(url) as conn:conn.execute('DROP SCHEMA '+schema+' CASCADE')


if __name__=='__main__':unittest.main()
