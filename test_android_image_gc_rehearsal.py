"""Synthetic PostgreSQL proof that orphan-only device-scoped PNG GC is safe."""
import inspect
import os
import unittest
import uuid

import android_image_gc_rehearsal as gc
import android_image_persistent_shadow as shadow
from test_android_image_persistent_shadow import png, batch, A, B


class NonProductionRules(unittest.TestCase):
    def test_public_schema_rejected_before_any_delete(self):
        class Result:
            def fetchone(self):return ('public',)
        class OnlySchema:
            def __init__(self):self.calls=[]
            def execute(self,sql,*_):
                self.calls.append(sql)
                if sql=="SELECT current_schema()":return Result()
                raise AssertionError("Unexpected SQL on public schema")
        conn=OnlySchema()
        with self.assertRaisesRegex(ValueError,"Isolated image GC rehearsal invalid"):
            gc.prune_orphans_in_test_schema(conn)
        self.assertEqual(conn.calls,["SELECT current_schema()"])

    def test_gc_has_no_runtime_hook_or_raw_image_export(self):
        code=inspect.getsource(gc)
        for forbidden in ('def start(', 'def do_POST(', 'def main(',
                          'VACUUM FULL', 'requests.post', 'BOB_IMAGE_GC_ENABLED'):
            self.assertNotIn(forbidden,code)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     "CI isolated PostgreSQL required")
class OrphanGcPostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],
                                  autocommit=True)
        self.schema='png_gc_'+uuid.uuid4().hex
        self.conn.execute('CREATE SCHEMA '+self.schema)
        self.conn.execute('SET search_path TO '+self.schema)
        self.conn.execute("""CREATE TABLE bob_android_list_images (
            batch_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),payload JSONB NOT NULL)""")
        shadow.init_test_schema(self.conn)
        common=png(b'original common screenshot')
        unique=png(b'original unique screenshot')
        self.a1=self.add(A,'1',common)
        self.a2=self.add(A,'2',common)
        self.a3=self.add(A,'3',unique)
        self.b1=self.add(B,'4',common)

    def tearDown(self):
        self.conn.execute('DROP SCHEMA '+self.schema+' CASCADE')
        self.conn.close()

    def add(self,owner,character,encoded):
        from psycopg.types.json import Jsonb
        value=batch(character,encoded)
        self.conn.execute("""INSERT INTO bob_android_list_images
             (batch_id,token_hash,payload) VALUES(%s,%s,%s)""",
             (value['batchId'],owner,Jsonb(value)))
        shadow.stage_copy_test_only(self.conn,value['batchId'],owner)
        return value

    def counts(self):
        return (self.conn.execute("SELECT count(*) FROM bob_android_shadow_objects").fetchone()[0],
                self.conn.execute("SELECT count(*) FROM bob_android_shadow_batch_refs").fetchone()[0])

    def test_uses_object_while_any_same_device_ref_still_exists(self):
        self.assertEqual(self.counts(),(3,4))
        self.conn.execute("DELETE FROM bob_android_list_images WHERE batch_id=%s",
                          (self.a1['batchId'],))
        self.assertEqual(self.counts(),(3,3))
        first=gc.prune_orphans_in_test_schema(self.conn)
        self.assertEqual(first['removedOrphanObjects'],0)
        self.assertFalse(first['sourceRowsDeleted'])
        self.assertIsNone(first['diskBytesFreed'])
        # Same-device second source still needs the PNG.
        self.assertEqual(shadow.verify_shadow(self.conn,self.a2['batchId'],A),
                         self.a2)
        self.conn.execute("DELETE FROM bob_android_list_images WHERE batch_id IN (%s,%s)",
                          (self.a2['batchId'],self.a3['batchId']))
        result=gc.prune_orphans_in_test_schema(self.conn)
        self.assertEqual(result['removedOrphanObjects'],2)
        self.assertEqual(result['retainedReferencedObjects'],1)
        self.assertEqual(self.counts(),(1,1))
        self.assertEqual(shadow.verify_shadow(self.conn,self.b1['batchId'],B),
                         self.b1)
        self.assertFalse(result['productionGarbageCollectorEnabled'])
        self.assertFalse(result['migrationAuthorized'])

    def test_expired_but_not_deleted_source_blocks_gc(self):
        original=self.counts()
        self.conn.execute("""UPDATE bob_android_list_images
            SET created_at=now()-interval '25 hours' WHERE batch_id=%s""",
            (self.a1['batchId'],))
        with self.assertRaises(ValueError):
            gc.prune_orphans_in_test_schema(self.conn)
        self.assertEqual(self.counts(),original)

    def test_corrupted_live_object_blocks_all_orphan_cleanup(self):
        self.conn.execute("DELETE FROM bob_android_list_images WHERE batch_id IN (%s,%s)",
                          (self.a2['batchId'],self.a3['batchId']))
        # B's device-private object is still referenced. Corrupt it and
        # ensure an unrelated A-orphan is NOT silently cleaned.
        self.conn.execute("""UPDATE bob_android_shadow_objects
            SET encoded_png='corrupted' WHERE token_hash=%s""",(B,))
        before=self.counts()
        with self.assertRaises(ValueError):
            gc.prune_orphans_in_test_schema(self.conn)
        self.assertEqual(self.counts(),before)

    def test_bad_pointer_ledger_fails_before_cleanup(self):
        self.conn.execute("DELETE FROM bob_android_list_images WHERE batch_id=%s",
                          (self.a3['batchId'],))
        self.conn.execute("""UPDATE bob_android_shadow_batch_refs
             SET pointer_payload='{}'::jsonb WHERE batch_id=%s""",
             (self.a1['batchId'],))
        before=self.counts()
        with self.assertRaises(ValueError):
            gc.prune_orphans_in_test_schema(self.conn)
        self.assertEqual(self.counts(),before)


if __name__=='__main__':
    unittest.main()
