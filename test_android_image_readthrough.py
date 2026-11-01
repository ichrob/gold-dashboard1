"""Original Android list responses/OCR must fail closed on bad image references."""
import base64
import copy
import json
import os
import struct
import time
import unittest
import uuid
from datetime import datetime,timezone
from unittest.mock import patch

import android_image_readthrough as reader
import android_image_persistent_shadow as shadow
import android_image_reference_codec as codec
import android_list
import handset_list_worker

OWNER_A='a'*64
OWNER_B='b'*64


def sample_png(tag):
    raw=(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'
         +struct.pack('>II',320,480)+b'\x08\x02\x00\x00\x00'+tag)
    return base64.b64encode(raw).decode()


def sample_batch(bid,now):
    return {'batchId':bid,'sessionId':'f'*32,
            'images':[{'at':datetime.fromtimestamp(now-10,timezone.utc).isoformat(),
                       'png':sample_png(b'private original image 1'),
                       'appText':{'before':['private evidence'],
                                  'after':['private evidence']}}]}


class CompatibilityUnitTests(unittest.TestCase):
    def test_raw_rows_stay_exact_and_do_not_call_database(self):
        value=sample_batch('1'*32,time.time())
        self.assertFalse(reader.is_reference(value))
        class NoSQL:
            def transaction(self):raise AssertionError('legacy should not query')
        self.assertIs(reader.materialize(NoSQL(),value['batchId'],value),value)

    def test_mixed_raw_and_pointer_cannot_be_returned_partially(self):
        value=sample_batch('1'*32,time.time())
        pointer,keyed=codec.pack_batch(value,OWNER_A)
        mixed=copy.deepcopy(value)
        mixed['images'][0][codec._REF]=pointer['images'][0][codec._REF]
        self.assertTrue(reader.is_reference(mixed))
        class NoSQL:
            def transaction(self):raise AssertionError('must reject shape first')
        with self.assertRaises(ValueError):
            reader.materialize(NoSQL(),value['batchId'],mixed)

    def test_reader_does_not_echo_private_sql_errors(self):
        value=sample_batch('1'*32,time.time())
        pointer,_=codec.pack_batch(value,OWNER_A)
        class BadDB:
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,*_):raise ValueError('private device token and PNG data')
        with self.assertRaisesRegex(ValueError,'Private image reference unavailable') as err:
            reader.materialize(BadDB(),value['batchId'],pointer)
        self.assertNotIn('device token',str(err.exception))

    def test_worker_materializes_before_ocr_without_exposing_pointer(self):
        bid='1'*32
        now=time.time()
        original=sample_batch(bid,now)
        pointer,_=codec.pack_batch(original,OWNER_A)
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class Conn:
            def __init__(self):self.writeStages=[];self.commits=0
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def commit(self):self.commits+=1
            def execute(self,sql,args=()):
                if sql.startswith('SELECT i.batch_id'):
                    return Result((bid,pointer,None,0,None))
                if 'processing_attempts=processing_attempts+1' in sql:
                    self.writeStages.append(json.loads(args[0])['stage'])
                if "SET import_receipt=%s" in sql:
                    self.writeStages.append(json.loads(args[0])['stage'])
                return Result(None)
        c=Conn()
        runner_calls=[]
        def runner(batch,at):
            runner_calls.append((batch,at))
            raise ValueError('OCR test sentinel')
        with patch('android_image_readthrough.materialize',return_value=original) as resolve:
            self.assertTrue(handset_list_worker.tick(lambda:c,runner))
        resolve.assert_called_once()
        self.assertEqual(runner_calls[0][0],original)
        self.assertEqual(runner_calls[0][1],original['images'][-1]['at'])
        self.assertEqual(c.writeStages,['reading','read-failed'])

    def test_missing_pointer_never_passes_to_ocr(self):
        bid='1'*32
        original=sample_batch(bid,time.time())
        pointer,_=codec.pack_batch(original,OWNER_A)
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class Conn:
            def __init__(self):self.receipts=[]
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def commit(self):pass
            def execute(self,sql,args=()):
                if sql.startswith('SELECT i.batch_id'):
                    return Result((bid,pointer,None,0,None))
                if 'SET import_receipt=%s' in sql:self.receipts.append(json.loads(args[0]))
                return Result(None)
        conn=Conn()
        with patch('android_image_readthrough.materialize',
                   side_effect=ValueError('private original missing')) as resolve:
            called=[]
            self.assertTrue(handset_list_worker.tick(lambda:conn,lambda *x:called.append(x)))
        self.assertEqual(called,[])
        self.assertEqual(conn.receipts[-1]['stage'],'read-failed')
        self.assertEqual(conn.receipts[-1]['error'],'ValueError')
        self.assertNotIn('private original',str(conn.receipts))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI integration')
class PostgresReferenceReaderTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.c=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True)
        self.schema='reader_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+self.schema)
        self.c.execute('SET search_path TO '+self.schema)
        self.c.execute('''CREATE TABLE bob_android_diagnostic_devices (
            token_hash TEXT PRIMARY KEY,revoked BOOLEAN NOT NULL DEFAULT FALSE,
            expires_at TIMESTAMPTZ NOT NULL)''')
        self.c.execute('''CREATE TABLE bob_android_list_images(
            batch_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload JSONB NOT NULL,parsed_items JSONB,import_receipt JSONB)''')
        shadow.init_test_schema(self.c)
        for owner in (OWNER_A,OWNER_B):
            self.c.execute('''INSERT INTO bob_android_diagnostic_devices
                (token_hash,expires_at) VALUES(%s,now()+interval '1 day')''',(owner,))

    def tearDown(self):
        self.c.execute('DROP SCHEMA '+self.schema+' CASCADE')
        self.c.close()

    def insert_raw(self,owner=OWNER_A,bid='1'*32):
        from psycopg.types.json import Jsonb
        data=sample_batch(bid,time.time())
        self.c.execute('''INSERT INTO bob_android_list_images
            (batch_id,token_hash,payload) VALUES(%s,%s,%s)''',
            (bid,owner,Jsonb(data)))
        return data

    def stage_pointer(self,owner=OWNER_A,bid='1'*32):
        from psycopg.types.json import Jsonb
        original=self.insert_raw(owner,bid)
        shadow.stage_copy_test_only(self.c,bid,owner)
        pointer=self.c.execute('''SELECT pointer_payload FROM
            bob_android_shadow_batch_refs WHERE batch_id=%s''',(bid,)).fetchone()[0]
        self.c.execute('''UPDATE bob_android_list_images SET payload=%s
            WHERE batch_id=%s''',(Jsonb(pointer),bid))
        return original,pointer

    def test_owned_reference_restores_full_batch_and_browser_list_get(self):
        original,pointer=self.stage_pointer()
        before=self.c.execute('SELECT created_at,parsed_items,import_receipt FROM bob_android_list_images').fetchone()
        restored=reader.materialize(self.c,original['batchId'],pointer)
        self.assertEqual(restored,original)
        result=android_list.handle(self.c,{'action':'list-get',
                                  'batchId':original['batchId']},time.time())
        self.assertEqual(result['batch'],original)
        self.assertEqual(result['items'],None)
        self.assertEqual(self.c.execute('SELECT created_at,parsed_items,import_receipt FROM bob_android_list_images').fetchone(),before)

    def test_raw_and_pointer_can_coexist_without_reader_switch(self):
        from psycopg.types.json import Jsonb
        original,pointer=self.stage_pointer()
        raw=self.insert_raw(bid='2'*32)
        a=android_list.handle(self.c,{'action':'list-get','batchId':'1'*32},time.time())
        b=android_list.handle(self.c,{'action':'list-get','batchId':'2'*32},time.time())
        self.assertEqual(a['batch'],original)
        self.assertEqual(b['batch'],raw)
        self.assertEqual(self.c.execute('SELECT payload FROM bob_android_list_images WHERE batch_id=%s',('1'*32,)).fetchone()[0],pointer)

    def test_ref_revoked_cross_device_and_missing_object_fail_closed(self):
        original,pointer=self.stage_pointer()
        bid=original['batchId']
        self.c.execute('UPDATE bob_android_diagnostic_devices SET revoked=TRUE WHERE token_hash=%s',(OWNER_A,))
        with self.assertRaises(ValueError):reader.materialize(self.c,bid,pointer)
        self.c.execute('UPDATE bob_android_diagnostic_devices SET revoked=FALSE WHERE token_hash=%s',(OWNER_A,))
        self.c.execute('UPDATE bob_android_shadow_batch_refs SET token_hash=%s WHERE batch_id=%s',(OWNER_B,bid))
        with self.assertRaises(ValueError):reader.materialize(self.c,bid,pointer)
        self.c.execute('UPDATE bob_android_shadow_batch_refs SET token_hash=%s WHERE batch_id=%s',(OWNER_A,bid))
        self.c.execute('DELETE FROM bob_android_shadow_objects')
        with self.assertRaises(ValueError):reader.materialize(self.c,bid,pointer)
        # Even when references fail, the stored source pointer isn't
        # silently presented as a complete, trusted original.
        self.assertEqual(self.c.execute('SELECT payload FROM bob_android_list_images').fetchone()[0],pointer)

    def test_wrong_pointer_and_expired_source_rejected(self):
        from psycopg.types.json import Jsonb
        original,pointer=self.stage_pointer()
        bid=original['batchId']
        tampered=copy.deepcopy(pointer)
        tampered['images'][0][codec._REF]='0'*64
        with self.assertRaises(ValueError):reader.materialize(self.c,bid,tampered)
        self.c.execute('''UPDATE bob_android_list_images SET created_at=
            now()-interval '25 hours' WHERE batch_id=%s''',(bid,))
        with self.assertRaises(ValueError):reader.materialize(self.c,bid,pointer)
