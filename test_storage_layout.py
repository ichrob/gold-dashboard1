import os
import unittest
import uuid
import storage_layout

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class LayoutTests(unittest.TestCase):
    def test_readonly_layout_adds_up_without_touching_originals(self):
        import psycopg
        schema='layout_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                c.execute('CREATE TABLE bob_diagnostic_history(id int primary key,stage text,payload jsonb)')
                c.execute("INSERT INTO bob_diagnostic_history SELECT i,'analysis',jsonb_build_object('value',i) FROM generate_series(1,1000)i")
                before=c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall()
                with c.transaction():
                    c.execute('SET TRANSACTION READ ONLY')
                    r=storage_layout.report(c)
                    self.assertEqual(r['status'],'observed')
                    t=r['tables'][0]
                    self.assertEqual(t['totalBytes'],sum(t[k] for k in ('heapBytes','indexBytes','toastBytes','otherBytes')))
                    self.assertTrue(r['indexes'][0]['valid'])
                    self.assertIsNone(r['reclaimableBytes'])
                    self.assertEqual(r['diagnosticPayloadSample']['status'],'sampled')
                self.assertEqual(c.execute('SELECT * FROM bob_diagnostic_history ORDER BY id').fetchall(),before)
                c.execute('DROP TABLE bob_diagnostic_history')
                with c.transaction():
                    r=storage_layout.report(c)
                    self.assertEqual(r['status'],'observed')
                    self.assertEqual(r['diagnosticPayloadSample']['status'],'not-observed')
                    self.assertEqual(c.execute('SELECT 1').fetchone()[0],1)
            finally:
                c.execute('DROP SCHEMA '+schema+' CASCADE')
