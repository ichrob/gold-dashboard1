"""Isolated one-batch PNG pointer transition, all-reader check and rollback."""
import inspect
import os
import unittest
import uuid

import android_image_pilot_rehearsal as rehearsal
import android_image_recovery_bundle as recovery
from test_android_image_recovery_bundle import BundleUnitTests


class SafetyTests(unittest.TestCase):
    def test_public_schema_fails_before_any_write_or_manifest_access(self):
        class Result:
            def fetchone(self):return ('public',)
        class OnlySchema:
            calls=[]
            def execute(self,query,*args):
                self.calls.append(query)
                if query=="SELECT current_schema()":return Result()
                raise AssertionError("Unsafe SQL")
        source=OnlySchema()
        with self.assertRaisesRegex(ValueError,"Isolated image CAS rehearsal invalid"):
            rehearsal.rehearse_test_schema(source,b'private', '0'*64)
        self.assertEqual(source.calls,["SELECT current_schema()"])

    def test_module_has_no_live_entrypoint_or_storage_reclamation(self):
        code=inspect.getsource(rehearsal)
        for forbidden in ('def start(', 'def do_POST(', 'def main(',
                          'VACUUM FULL', 'requests.post', 'deleteOriginals',
                          'BOB_PNG_PILOT_ENABLED', 'def cycle('):
            self.assertNotIn(forbidden,code)


@unittest.skipUnless(os.environ.get("BOB_TEST_DATABASE_URL"),
                     "PostgreSQL CI integration only")
class TestSchemaPilotTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn=psycopg.connect(os.environ["BOB_TEST_DATABASE_URL"],
                                  autocommit=True)
        self.schema="png_restore_"+uuid.uuid4().hex
        self.conn.execute("CREATE SCHEMA "+self.schema)
        self.conn.execute("SET search_path TO "+self.schema)
        self.conn.execute("""CREATE TABLE bob_android_diagnostic_devices (
            token_hash TEXT PRIMARY KEY, revoked BOOLEAN NOT NULL DEFAULT FALSE,
            expires_at TIMESTAMPTZ NOT NULL)""")
        self.conn.execute("""CREATE TABLE bob_android_list_images (
            batch_id TEXT PRIMARY KEY,token_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,payload JSONB NOT NULL,
            import_receipt JSONB,parsed_items JSONB,processing_at TIMESTAMPTZ,
            processing_attempts INTEGER NOT NULL)""")
        helper=BundleUnitTests()
        manifest=helper.manifest()
        self.blob,self.sha=helper.make_bundle(manifest)
        self.manifest=manifest
        self.conn.execute("""INSERT INTO bob_android_diagnostic_devices
            (token_hash,expires_at) VALUES (%s,now()+interval '1 day')""",
            (manifest['deviceScope'],))
        recovery.restore_to_isolated_test_schema(self.conn,self.blob,self.sha)

    def tearDown(self):
        self.conn.execute("DROP SCHEMA "+self.schema+" CASCADE")
        self.conn.close()

    def source(self):
        return self.conn.execute("""SELECT created_at,payload,import_receipt,
              parsed_items,processing_at,processing_attempts
              FROM bob_android_list_images""").fetchone()

    def test_pointer_readthrough_and_cas_original_restoration(self):
        original=self.source()
        r=rehearsal.rehearse_test_schema(self.conn,self.blob,self.sha)
        self.assertEqual(r['status'],'isolated-cas-rollback-rehearsal-verified')
        self.assertTrue(r['sourceRestored'])
        self.assertTrue(r['browserReaderVerified'])
        self.assertTrue(r['metadataPreserved'])
        self.assertEqual(r['rehearsedImages'],1)
        self.assertFalse(r['productionWriterInstalled'])
        self.assertFalse(r['migrationAuthorized'])
        self.assertFalse(r['deletionAuthorized'])
        self.assertIsNone(r['diskBytesFreed'])
        self.assertEqual(self.source(),original)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM bob_android_shadow_batch_refs").fetchone()[0],1)
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM bob_android_shadow_objects").fetchone()[0],1)

    def test_revoked_device_never_replaces_source(self):
        original=self.source()
        self.conn.execute("UPDATE bob_android_diagnostic_devices SET revoked=TRUE")
        with self.assertRaises(ValueError):
            rehearsal.rehearse_test_schema(self.conn,self.blob,self.sha)
        self.assertEqual(self.source(),original)

    def test_missing_object_fails_before_cas(self):
        original=self.source()
        self.conn.execute("DELETE FROM bob_android_shadow_objects")
        with self.assertRaises(ValueError):
            rehearsal.rehearse_test_schema(self.conn,self.blob,self.sha)
        self.assertEqual(self.source(),original)

    def test_changed_processing_metadata_not_accepted(self):
        self.conn.execute("""UPDATE bob_android_list_images
                           SET processing_attempts=processing_attempts+1""")
        current=self.source()
        with self.assertRaises(ValueError):
            rehearsal.rehearse_test_schema(self.conn,self.blob,self.sha)
        self.assertEqual(self.source(),current)

    def test_missing_reference_fails_without_touching_original(self):
        original=self.source()
        self.conn.execute("DELETE FROM bob_android_shadow_batch_refs")
        with self.assertRaises(ValueError):
            rehearsal.rehearse_test_schema(self.conn,self.blob,self.sha)
        self.assertEqual(self.source(),original)


if __name__=="__main__":
    unittest.main()
