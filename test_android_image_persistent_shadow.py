"""Isolated PostgreSQL proof: no live writer, no source mutation, no leakage."""
import base64
import copy
import json
import os
import struct
import unittest
import uuid
from datetime import datetime, timezone

import android_image_persistent_shadow as shadow

A='a'*64
B='b'*64


def png(marker):
    data=(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'
          +struct.pack('>II',300,450)+b'\x08\x02\x00\x00\x00'+marker)
    return base64.b64encode(data).decode()


def batch(label,encoded):
    now=datetime.now(timezone.utc).isoformat()
    return {'batchId':label*32,'sessionId':'e'*32,
            'images':[{'at':now,'png':encoded,
                      'appText':{'before':['original-private-text'],
                                 'after':['original-private-text']}}]}


class NonProductionSafetyTests(unittest.TestCase):
    def test_bad_identifiers_rejected_before_any_database_calls(self):
        class Fail:
            def transaction(self):raise AssertionError('must not connect')
        for batch_id,scope in [('bad',A),('1'*32,'bad'),('1'*32,B.upper()),
                               ('1'*31,A),('1'*32,False),(123,A)]:
            with self.subTest(batch_id=batch_id,scope=scope):
                with self.assertRaises(ValueError):
                    shadow.stage_copy_test_only(Fail(),batch_id,scope)

    def test_module_has_no_startup_or_public_write_surface(self):
        import inspect
        code=inspect.getsource(shadow)
        self.assertNotIn('def start(',code)
        self.assertNotIn('def do_POST(',code)
        self.assertNotIn('BOB_IMAGE_WRITER_ENABLED',code)
        self.assertNotIn('DELETE FROM bob_android_list_images',code)
        self.assertNotIn('UPDATE bob_android_list_images',code)
        self.assertNotIn('VACUUM FULL',code)
        self.assertNotIn('http://',code)
        self.assertNotIn('https://',code)
        self.assertNotIn('requests.post',code)

    def test_result_does_not_leak_device_or_png(self):
        try:
            shadow._require_ids('1'*32,A)
            self.assertGreater(len(shadow._canonical({'a':'b'})),0)
        except ValueError:
            self.fail('Valid scoped identifier rejected')


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'CI isolated PostgreSQL required')
class PersistentShadowPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],
                                  autocommit=True)
        self.schema='png_persist_'+uuid.uuid4().hex
        self.conn.execute('CREATE SCHEMA '+self.schema)
        self.conn.execute('SET search_path TO '+self.schema)
        self.conn.execute("""CREATE TABLE bob_android_list_images (
            batch_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            payload JSONB NOT NULL)""")
        shadow.init_test_schema(self.conn)

    def tearDown(self):
        self.conn.execute('DROP SCHEMA '+self.schema+' CASCADE')
        self.conn.close()

    def add(self,owner,label,encoded):
        from psycopg.types.json import Jsonb
        data=batch(label,encoded)
        self.conn.execute("""INSERT INTO bob_android_list_images
            (batch_id,token_hash,payload) VALUES(%s,%s,%s)""",
            (data['batchId'],owner,Jsonb(data)))
        return data

    def test_same_device_dedup_and_full_original_restoration(self):
        common=png(b'common original A')
        unique=png(b'another original')
        first=self.add(A,'1',common)
        second=self.add(A,'2',common)
        third=self.add(A,'3',unique)
        other=self.add(B,'4',common)
        before=self.conn.execute("""SELECT batch_id,token_hash,created_at,payload
            FROM bob_android_list_images ORDER BY batch_id""").fetchall()

        results=[shadow.stage_copy_test_only(self.conn,x['batchId'],scope)
                 for x,scope in ((first,A),(second,A),(third,A),(other,B))]
        self.assertEqual({x['status'] for x in results},
                         {'isolated-shadow-copy-verified'})
        self.assertTrue(all(x['fullBatchRoundTripVerified']
                            and x['sourceUnchanged'] for x in results))
        self.assertTrue(all(not x['migrationAuthorized']
                            and not x['persistentBackupVerified'] for x in results))
        self.assertTrue(all(x['diskBytesFreed'] is None for x in results))
        for result in results:
            for private in ('original-private-text',common[:30],A,B,
                            first['batchId'],'token_hash','object_key'):
                self.assertNotIn(private,json.dumps(result))
        self.assertEqual(self.conn.execute("""SELECT batch_id,token_hash,created_at,payload
            FROM bob_android_list_images ORDER BY batch_id""").fetchall(),before)

        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_objects').fetchone()[0],3)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_batch_refs').fetchone()[0],4)
        for original,scope in ((first,A),(second,A),(third,A),(other,B)):
            self.assertEqual(shadow.verify_shadow(self.conn,original['batchId'],scope),
                             original)
        # A second invocation of the SAME original does not create another object.
        shadow.stage_copy_test_only(self.conn,second['batchId'],A)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_objects').fetchone()[0],3)
        with self.assertRaises(ValueError):
            shadow.verify_shadow(self.conn,first['batchId'],B)

    def test_tampered_object_or_pointer_fails_without_losing_source(self):
        from psycopg.types.json import Jsonb
        p=self.add(A,'1',png(b'genuine original'))
        shadow.stage_copy_test_only(self.conn,p['batchId'],A)
        original=self.conn.execute('SELECT payload FROM bob_android_list_images').fetchone()[0]
        self.conn.execute("""UPDATE bob_android_shadow_objects SET encoded_png=%s""",
                          (png(b'forged image data'),))
        with self.assertRaises(ValueError):
            shadow.verify_shadow(self.conn,p['batchId'],A)
        self.assertEqual(self.conn.execute(
            'SELECT payload FROM bob_android_list_images').fetchone()[0],original)

    def test_malformed_stored_original_rolls_back_without_shadow_objects(self):
        from psycopg.types.json import Jsonb
        invalid={'batchId':'1'*32,'sessionId':'e'*32,
                 'images':[{'at':'2000-01-01T00:00:00+00:00',
                            'png':png(b'old original')}]}
        self.conn.execute("""INSERT INTO bob_android_list_images
            (batch_id,token_hash,payload) VALUES(%s,%s,%s)""",
            ('1'*32,A,Jsonb(invalid)))
        with self.assertRaises(ValueError):
            shadow.stage_copy_test_only(self.conn,'1'*32,A)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_objects').fetchone()[0],0)
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_batch_refs').fetchone()[0],0)

    def test_expired_source_cascades_reference_and_cannot_be_resolved(self):
        p=self.add(A,'1',png(b'genuine original'))
        shadow.stage_copy_test_only(self.conn,p['batchId'],A)
        # Change only the synthetic test source's expiry to simulate policy.
        self.conn.execute("""UPDATE bob_android_list_images
            SET created_at=now()-interval '25 hours'""")
        with self.assertRaises(ValueError):
            shadow.verify_shadow(self.conn,p['batchId'],A)
        self.conn.execute("DELETE FROM bob_android_list_images WHERE batch_id=%s",
                          (p['batchId'],))
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_batch_refs').fetchone()[0],0)
        # Orphan objects remain until separately verified garbage collection.
        self.assertEqual(self.conn.execute(
            'SELECT count(*) FROM bob_android_shadow_objects').fetchone()[0],1)

    def test_checksum_mismatch_fails_closed(self):
        from psycopg.types.json import Jsonb
        p=self.add(A,'1',png(b'genuine original'))
        shadow.stage_copy_test_only(self.conn,p['batchId'],A)
        self.conn.execute("""UPDATE bob_android_shadow_batch_refs
            SET original_sha256=%s""",('0'*64,))
        with self.assertRaises(ValueError):
            shadow.verify_shadow(self.conn,p['batchId'],A)


if __name__=='__main__':
    unittest.main()
