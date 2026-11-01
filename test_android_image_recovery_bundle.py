"""Private image recovery package tests: exact source+metadata and isolated restore."""
import base64
import copy
import gzip
import hashlib
import json
import os
import struct
import unittest
import uuid
from datetime import datetime,timezone

import android_image_recovery_bundle as recovery
import android_image_persistent_shadow as shadow

A='a'*64
B='b'*64


def png(marker):
    raw=(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'
         +struct.pack('>II',384,640)+b'\x08\x02\x00\x00\x00'
         +marker)
    return base64.b64encode(raw).decode()


def original(batch_id):
    return {'batchId':batch_id,'sessionId':'e'*32,
            'images':[{'at':datetime.now(timezone.utc).isoformat(),
                       'png':png(b'private full original PNG data'),
                       'appText':{'before':['private trading app text'],
                                  'after':['private trading app text']}}]}


class BundleUnitTests(unittest.TestCase):
    def manifest(self):
        import android_image_reference_codec as codec
        batch=original('1'*32)
        pointer,objects=codec.pack_batch(batch,A)
        return {
            'format':recovery._FORMAT,'deviceScope':A,'batchId':'1'*32,
            'uploadedAt':datetime.now(timezone.utc).isoformat(),
            'original':batch,
            'sourceMetadata':{'importReceipt':{'stage':'synced','count':10},
                              'parsedItems':[{'isin':'private original ISIN'}],
                              'processingAt':datetime.now(timezone.utc).isoformat(),
                              'processingAttempts':2},
            'reference':pointer,
            'objects':[{'key':key,'encodedPng':encoded}
                       for key,encoded in objects.items()],
            'originalSha256':hashlib.sha256(recovery._canonical(batch)).hexdigest(),
        }

    def make_bundle(self,obj):
        raw=recovery._canonical(obj)
        blob=gzip.compress(raw,mtime=0)
        return blob,hashlib.sha256(blob).hexdigest()

    def test_checksum_and_bytewise_identical_private_manifest(self):
        obj=self.manifest()
        blob,checksum=self.make_bundle(obj)
        result=recovery.validate_recovery_bundle(blob,checksum)
        self.assertEqual(result,obj)
        self.assertNotEqual(blob[:2],b'{')
        self.assertEqual(gzip.decompress(blob),recovery._canonical(obj))
        self.assertNotIn(b'private original ISIN',blob[:150])

    def test_tampering_and_cross_scope_fail_even_with_resigned_checksum(self):
        good=self.manifest()
        tests=[]
        modified=copy.deepcopy(good)
        modified['objects'][0]['encodedPng']=png(b'tampered PNG content')
        tests.append(modified)
        modified=copy.deepcopy(good)
        modified['deviceScope']=B
        tests.append(modified)
        modified=copy.deepcopy(good)
        modified['sourceMetadata']['importReceipt']['stage']='reading'
        # Changing receipt alone is not a byte error: exact receipt is an
        # independent field of the source manifest, not part of PNG SHA.
        self.assertEqual(recovery.validate_recovery_bundle(
            *self.make_bundle(modified))['sourceMetadata']['importReceipt']['stage'],
            'reading')
        modified=copy.deepcopy(good)
        modified['objects'].append(dict(modified['objects'][0]))
        tests.append(modified)
        modified=copy.deepcopy(good)
        modified['original']['sessionId']='0'*32
        tests.append(modified)
        modified=copy.deepcopy(good)
        modified['unknownSecret']='private'
        tests.append(modified)
        modified=copy.deepcopy(good)
        modified['sourceMetadata']['processingAttempts']=-1
        tests.append(modified)
        for m in tests:
            with self.subTest(change=m):
                blob,checksum=self.make_bundle(m)
                with self.assertRaisesRegex(ValueError,'Recovery artifact invalid'):
                    recovery.validate_recovery_bundle(blob,checksum)
        blob,checksum=self.make_bundle(good)
        bad=blob[:-1]+bytes([blob[-1]^1])
        with self.assertRaises(ValueError):
            recovery.validate_recovery_bundle(bad,checksum)
        with self.assertRaises(ValueError):
            recovery.validate_recovery_bundle(blob,'0'*64)
        with self.assertRaises(ValueError):
            recovery.validate_recovery_bundle(blob+b'x',checksum)

    def test_decompression_limits_and_corrupt_stream(self):
        data=b'A'*(recovery._RAW_LIMIT+100)
        blob=gzip.compress(data)
        with self.assertRaises(ValueError):
            recovery.validate_recovery_bundle(blob,hashlib.sha256(blob).hexdigest())
        blob=b'garbage data'
        with self.assertRaises(ValueError):
            recovery.validate_recovery_bundle(blob,hashlib.sha256(blob).hexdigest())

    def test_restore_requires_explicit_isolated_schema(self):
        data=self.manifest()
        blob,checksum=self.make_bundle(data)
        class Guard:
            def execute(self,sql,*args):
                if sql=='SELECT current_schema()':
                    class Result:
                        def fetchone(self):return ('public',)
                    return Result()
                raise AssertionError('Must never write to production')
        with self.assertRaisesRegex(ValueError,'Separate test restore schema'):
            recovery.restore_to_isolated_test_schema(Guard(),blob,checksum)

    def test_module_does_not_expose_production_job_or_network(self):
        import inspect
        code=inspect.getsource(recovery)
        for marker in ('def start(', 'def do_POST(', 'GoogleDrive(',
                       'requests.post(', 'BOB_IMAGE_WRITER_ENABLED',
                       'DELETE FROM bob_android_list_images',
                       'VACUUM FULL'):
            self.assertNotIn(marker,code)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'Isolated PostgreSQL integration required')
class PostgresRecoveryTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.dsn=os.environ['BOB_TEST_DATABASE_URL']
        self.source_schema='png_source_'+uuid.uuid4().hex
        self.dest_schema='png_restore_'+uuid.uuid4().hex
        self.source=psycopg.connect(self.dsn,autocommit=True)
        self.dest=psycopg.connect(self.dsn,autocommit=True)
        self.source.execute('CREATE SCHEMA '+self.source_schema)
        self.dest.execute('CREATE SCHEMA '+self.dest_schema)
        for conn,schema in ((self.source,self.source_schema),
                            (self.dest,self.dest_schema)):
            conn.execute('SET search_path TO '+schema)
            conn.execute("""CREATE TABLE bob_android_list_images (
                batch_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                payload JSONB NOT NULL,import_receipt JSONB,
                parsed_items JSONB,processing_at TIMESTAMPTZ,
                processing_attempts INTEGER NOT NULL DEFAULT 0)""")
        shadow.init_test_schema(self.source)

    def tearDown(self):
        self.source.execute('DROP SCHEMA '+self.source_schema+' CASCADE')
        self.dest.execute('DROP SCHEMA '+self.dest_schema+' CASCADE')
        self.source.close()
        self.dest.close()

    def add(self,scope=A,bid='1'*32):
        from psycopg.types.json import Jsonb
        row=original(bid)
        metadata={'stage':'synced','count':10,'at':'source-original'}
        items=[{'isin':'DE000PRIVATE','evidence':'unaltered'}]
        at=datetime.now(timezone.utc)
        self.source.execute("""INSERT INTO bob_android_list_images
            (batch_id,token_hash,payload,import_receipt,
             parsed_items,processing_at,processing_attempts)
            VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (bid,scope,Jsonb(row),Jsonb(metadata),Jsonb(items),at,2))
        shadow.stage_copy_test_only(self.source,bid,scope)
        return row

    def test_restore_source_and_reference_from_bundle_in_separate_schema(self):
        before_row=self.add()
        before=self.source.execute("""SELECT batch_id,token_hash,created_at,
            payload,import_receipt,parsed_items,processing_at,processing_attempts
            FROM bob_android_list_images""").fetchone()
        bundle,sha=recovery.pack_recovery_bundle(self.source,'1'*32,A)
        self.assertLess(len(bundle),recovery._BLOB_LIMIT)
        # The isolated destination is separate from source: no source query
        # inside restore, and no production write API is invoked.
        result=recovery.restore_to_isolated_test_schema(self.dest,bundle,sha)
        self.assertEqual(result['status'],'isolated-test-restore-verified')
        self.assertTrue(result['fullBatchRoundTripVerified'])
        self.assertFalse(result['independentServerVerified'])
        self.assertFalse(result['remoteDownloadVerified'])
        self.assertFalse(result['encryptionVerified'])
        self.assertFalse(result['deletionAuthorized'])
        self.assertIsNone(result['diskBytesFreed'])
        self.assertNotIn('private',json.dumps(result))
        after=self.dest.execute("""SELECT batch_id,token_hash,created_at,
            payload,import_receipt,parsed_items,processing_at,processing_attempts
            FROM bob_android_list_images""").fetchone()
        self.assertEqual(before,after)
        self.assertEqual(shadow._resolve(self.dest,'1'*32,A),before_row)
        self.assertEqual(self.source.execute("""SELECT batch_id,token_hash,created_at,
            payload,import_receipt,parsed_items,processing_at,processing_attempts
            FROM bob_android_list_images""").fetchone(),before)
        self.assertEqual(self.dest.execute(
            'SELECT count(*) FROM bob_android_shadow_objects').fetchone()[0],1)
        self.assertEqual(self.dest.execute(
            'SELECT count(*) FROM bob_android_shadow_batch_refs').fetchone()[0],1)

    def test_corrupted_reference_or_scope_never_exports(self):
        from psycopg.types.json import Jsonb
        self.add()
        self.source.execute("""UPDATE bob_android_shadow_batch_refs
            SET original_sha256=%s""",('0'*64,))
        with self.assertRaises(ValueError):
            recovery.pack_recovery_bundle(self.source,'1'*32,A)
        self.assertEqual(self.dest.execute(
            'SELECT count(*) FROM bob_android_list_images').fetchone()[0],0)
        with self.assertRaises(ValueError):
            recovery.pack_recovery_bundle(self.source,'1'*32,B)

    def test_existing_destination_never_overwritten(self):
        self.add()
        bundle,sha=recovery.pack_recovery_bundle(self.source,'1'*32,A)
        first=recovery.restore_to_isolated_test_schema(self.dest,bundle,sha)
        self.assertTrue(first['fullBatchRoundTripVerified'])
        original_dest=self.dest.execute(
            'SELECT payload FROM bob_android_list_images').fetchone()[0]
        with self.assertRaises(Exception):
            recovery.restore_to_isolated_test_schema(self.dest,bundle,sha)
        self.assertEqual(self.dest.execute(
            'SELECT count(*) FROM bob_android_list_images').fetchone()[0],1)
        self.assertEqual(self.dest.execute(
            'SELECT payload FROM bob_android_list_images').fetchone()[0],original_dest)


if __name__=='__main__':
    unittest.main()
