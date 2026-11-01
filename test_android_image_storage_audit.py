"""No screenshot, digest, session or device identity leaves private diagnostics."""
import base64
import json
import os
import unittest
import uuid
from unittest.mock import patch
import android_image_storage_audit as audit


class AuditUnitTests(unittest.TestCase):
    def test_aggregate_only_and_no_false_disk_savings(self):
        result=audit._counts((3,5,150,2,60), 1793538000)
        self.assertEqual(result['status'],'sampled')
        self.assertEqual(result['sampledImages'],5)
        self.assertEqual(result['candidateRepeatedImages'],2)
        self.assertEqual(result['candidateRepeatedEncodedCharacters'],60)
        self.assertFalse(result['exactDuplicateProven'])
        self.assertIsNone(result['diskBytesFreed'])
        self.assertIsNone(result['reclaimableBytes'])
        for private in ('batchId','sessionId','token_hash','png','sha256',
                        'file_id','isin','account','md5Digest'):
            self.assertNotIn(private,json.dumps(result))

    def test_bad_results_rejected_and_empty_distinct(self):
        self.assertEqual(audit._counts((0,0,0,0,0),1)['status'],'empty')
        for row in ((9,9,90,0,0),(1,5,50,0,0),(1,1,10,2,10),
                    (1,1,10,0,11),(1,1,True,0,0),('private',0,0,0,0),
                    (1,1,1,1),(None,0,0,0,0)):
            with self.subTest(row=row):
                self.assertEqual(audit._counts(row,1)['status'],'not-observed')

    def test_cached_read_only_sql_and_timeout(self):
        class Query:
            def __init__(self):self.calls=[]
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,sql):
                self.calls.append(sql)
                return self
            def fetchone(self):return (2,3,30,1,10)
        conn=Query()
        with patch.object(audit,'_cache',None),patch.object(audit,'_cached_at',0):
            first=audit.report(conn,now=1000000)
            second=audit.report(conn,now=1000060)
            self.assertEqual(first,second)
            self.assertEqual(len(conn.calls),3)
        self.assertEqual(first['status'],'sampled')
        self.assertIn("LIMIT 8",audit._SQL)
        self.assertIn("created_at >= now()-interval '24 hours'",audit._SQL)
        self.assertIn("md5(",audit._SQL)
        self.assertIn("SET LOCAL statement_timeout='1500ms'",conn.calls)
        self.assertFalse(any('DELETE FROM' in s or 'UPDATE ' in s or
                             'VACUUM ' in s or 'CREATE TABLE' in s for s in conn.calls))

    def test_exact_verification_refuses_modified_cohort_and_large_sample(self):
        summary=audit._counts((2,2,20,1,10),100)
        class Cohort:
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,_):return self
            def fetchall(self):return [('missing',)]
        result=audit._verify_exact(Cohort(),summary)
        self.assertEqual(result['exactVerificationStatus'],'cohort-changed')
        self.assertFalse(result['exactDuplicateProven'])
        oversized={**summary,'totalEncodedImageCharacters':12_000_001}
        self.assertEqual(audit._verify_exact(Cohort(),oversized)['exactVerificationStatus'],
                         'sample-too-large')
        self.assertFalse(audit._verify_exact(Cohort(),oversized)['exactDuplicateProven'])

    def test_permission_error_never_exposes_original(self):
        class Broken:
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,_):raise PermissionError('secret screenshot /private')
        with patch.object(audit,'_cache',None),patch.object(audit,'_cached_at',0):
            result=audit.report(Broken(),now=1000000)
        self.assertEqual(result['status'],'not-observed')
        self.assertNotIn('secret screenshot',str(result))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'PostgreSQL CI integration required')
class PostgresAuditTests(unittest.TestCase):
    def test_reports_repeat_candidates_but_preserves_private_pngs(self):
        import psycopg
        from psycopg.types.json import Jsonb
        schema='image_dup_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                c.execute('''CREATE TABLE bob_android_list_images (
                    batch_id text PRIMARY KEY,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    payload jsonb NOT NULL)''')
                raw_a=bytes.fromhex('89504e470d0a1a0a')+b'private PNG A'
                raw_b=bytes.fromhex('89504e470d0a1a0a')+b'private PNG B'
                raw_c=bytes.fromhex('89504e470d0a1a0a')+b'private PNG C'
                a=base64.b64encode(raw_a).decode()
                b=base64.b64encode(raw_b).decode()
                distinct=base64.b64encode(raw_c).decode()
                data=[
                    {'images':[{'png':a},{'png':b}]},
                    {'images':[{'png':a}]},
                    {'images':[{'png':distinct}]}
                ]
                for idx,row in enumerate(data):
                    c.execute('INSERT INTO bob_android_list_images(batch_id,payload) VALUES(%s,%s)',
                              (str(idx),Jsonb(row)))
                before=c.execute('SELECT batch_id,payload FROM bob_android_list_images ORDER BY batch_id').fetchall()
                with patch.object(audit,'_cache',None),patch.object(audit,'_cached_at',0):
                    with c.transaction():
                        c.execute('SET TRANSACTION READ ONLY')
                        report=audit.report(c)
                self.assertEqual(report['status'],'sampled')
                self.assertEqual(report['sampledBatches'],3)
                self.assertEqual(report['sampledImages'],4)
                self.assertEqual(report['candidateRepeatedImages'],1)
                self.assertEqual(report['candidateRepeatedEncodedCharacters'],len(a))
                self.assertEqual(report['totalEncodedImageCharacters'],
                                 len(a)*2+len(b)+len(distinct))
                self.assertNotIn(a,json.dumps(report))
                self.assertNotIn(b,json.dumps(report))
                self.assertTrue(report['exactDuplicateProven'])
                self.assertEqual(report['exactVerificationStatus'],'verified')
                self.assertEqual(report['exactDuplicateImages'],1)
                self.assertEqual(report['exactRepeatedEncodedCharacters'],len(a))
                self.assertEqual(report['exactRepeatedPngBytes'],len(raw_a))
                self.assertNotIn(distinct,json.dumps(report))
                self.assertEqual(c.execute('SELECT batch_id,payload FROM bob_android_list_images ORDER BY batch_id').fetchall(),before)
            finally:
                c.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_absent_android_table_is_nonfatal(self):
        import psycopg
        schema='image_empty_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                with patch.object(audit,'_cache',None),patch.object(audit,'_cached_at',0):
                    result=audit.report(c)
                self.assertEqual(result['status'],'not-observed')
                self.assertIsNone(result['diskBytesFreed'])
            finally:
                c.execute('DROP SCHEMA '+schema+' CASCADE')


if __name__=='__main__':
    unittest.main()
