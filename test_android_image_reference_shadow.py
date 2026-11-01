"""Read-only shadow proves exact originals without migrations or output secrets."""
import base64
import copy
import json
import os
import struct
import time
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import android_image_reference_shadow as shadow

A='a'*64
B='b'*64


def png(marker):
    raw=(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'
         +struct.pack('>II',256,512)+b'\x08\x02\x00\x00\x00'
         +marker)
    return base64.b64encode(raw).decode()


def batch(ch,source,now):
    stamp=datetime.fromtimestamp(now-20,timezone.utc).isoformat()
    return {'batchId':ch*32,'sessionId':'e'*32,
            'images':[{'at':stamp,'png':source,
                       'appText':{'before':['private original text'],
                                  'after':['private original text']}}]}


class ShadowSafetyTests(unittest.TestCase):
    def test_shadow_preserves_exact_original_and_device_scope(self):
        now=time.time()
        shared=png(b'a'*4000)
        other=png(b'b'*1000)
        at=datetime.fromtimestamp(now,timezone.utc)
        records=[(A,at,batch('1',shared,now)),
                 (A,at,batch('2',shared,now)),
                 (B,at,batch('3',shared,now)),
                 (A,at,batch('4',other,now))]
        original=copy.deepcopy(records)
        result=shadow._simulate(records,now)
        self.assertEqual(records,original)
        self.assertEqual(result['status'],'verified-in-memory')
        self.assertTrue(result['fullBatchRoundTripVerified'])
        self.assertEqual(result['sampledBatches'],4)
        self.assertEqual(result['sampledImages'],4)
        self.assertEqual(result['deviceScopeCount'],2)
        self.assertEqual(result['uniqueScopedImageObjects'],3)
        self.assertEqual(result['repeatedImageReferences'],1)
        self.assertGreater(result['serializedJsonDifferenceBytes'],0)
        self.assertFalse(result['persistentBackupVerified'])
        self.assertFalse(result['migrationAuthorized'])
        self.assertIsNone(result['diskBytesFreed'])
        self.assertIsNone(result['reclaimableBytes'])
        for private in ('private original','batchId','sessionId','png',
                        shared[:70],A,B,'fileId','token_hash'):
            self.assertNotIn(private,json.dumps(result))

    def test_stale_or_unauthenticated_clock_fails_closed(self):
        now=time.time()
        source=png(b'1'*200)
        old=datetime.fromtimestamp(now-2*86400,timezone.utc)
        naive=datetime.fromtimestamp(now)
        for clock in (old,naive,None):
            result=shadow._simulate([(A,clock,batch('1',source,now))],now)
            self.assertEqual(result['status'],'not-observed')
            self.assertIsNone(result['diskBytesFreed'])

    def test_missing_or_bad_scope_fails_closed(self):
        now=time.time()
        sample=png(b'1'*200)
        at=datetime.fromtimestamp(now,timezone.utc)
        for rows in ([('bad',at,batch('1',sample,now))],
                     [(A,at,{'batchId':'bad','images':[]})],
                     [(A,at,batch('1',sample,now))]*9,
                     [(A,at,batch('1','wrong',now))]):
            with self.subTest(num=len(rows)):
                result=shadow._simulate(rows,now)
            self.assertEqual(result['status'],'not-observed')
            self.assertIsNone(result['diskBytesFreed'])

    def test_same_decoded_png_but_ambiguous_encoding_must_not_share(self):
        now=time.time()
        source=png(b'x'*500)
        # Base64 permits normalization variations only if decoder accepts both.
        # Even when that occurs, a content key alone cannot restore the exact
        # original encoded text; a future writer must store that difference.
        original=base64.b64decode(source)
        alternative=base64.b64encode(original).decode()
        self.assertEqual(source,alternative)
        self.assertEqual(shadow._simulate(
            [(A,datetime.fromtimestamp(now,timezone.utc),batch('1',source,now)),
             (A,datetime.fromtimestamp(now,timezone.utc),batch('2',alternative,now))],
            now)['status'],'verified-in-memory')

    def test_empty_and_oversized_and_invalid_return_no_savings(self):
        self.assertEqual(shadow._simulate([],time.time())['status'],'empty')
        now=time.time()
        source=png(b'a'*1000)
        with patch.object(shadow,'_MAX_ENCODED',10):
            result=shadow._simulate([(A,datetime.fromtimestamp(now,timezone.utc),batch('1',source,now))],now)
        self.assertEqual(result['status'],'sample-too-large')
        self.assertNotIn('serializedJsonDifferenceBytes',result)

    def test_read_only_sql_cache_and_restricted_errors(self):
        now=time.time()
        source=png(b'c'*300)
        class Conn:
            def __init__(self):self.queries=[]
            def transaction(self):return self
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,sql):
                self.queries.append(sql)
                return self
            def fetchone(self):
                return (1,len(json.dumps(batch('1',source,now)))+10)
            def fetchall(self):
                return [(A,datetime.fromtimestamp(now,timezone.utc),batch('1',source,now))]
        c=Conn()
        with patch.object(shadow,'_cache',None),patch.object(shadow,'_cache_at',0):
            a=shadow.report(c,now=now)
            b=shadow.report(c,now=now+60)
        self.assertEqual(a,b)
        self.assertEqual(a['status'],'verified-in-memory')
        self.assertEqual(len(c.queries),4)
        self.assertIn('LIMIT 8',shadow._SQL)
        self.assertIn('LIMIT 8',shadow._PROBE)
        self.assertIn('14000000',shadow._SQL)
        self.assertIn("SET LOCAL statement_timeout='2500ms'",c.queries)
        self.assertIn('coalesce(sum(octet_length(payload::text)),0)',shadow._PROBE)
        self.assertIn("SET LOCAL lock_timeout='500ms'",c.queries)
        self.assertTrue(all(not any(w in q for w in
                         ('DELETE ','UPDATE ','INSERT ','VACUUM ','CREATE TABLE'))
                         for q in c.queries))
        class Broken(Conn):
            def execute(self,sql):raise RuntimeError('secret private raw screenshot')
        with patch.object(shadow,'_cache',None),patch.object(shadow,'_cache_at',0):
            r=shadow.report(Broken(),now=now)
        self.assertEqual(r['status'],'not-observed')
        self.assertNotIn('secret private',str(r))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'Isolated PostgreSQL integration only')
class DatabaseShadowTests(unittest.TestCase):
    def test_postgresql_8_batch_shadow_keeps_every_jsonb_original(self):
        import psycopg
        from psycopg.types.json import Jsonb
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        schema='shadow_'+uuid.uuid4().hex
        now=time.time()
        shared=png(b's'*2000)
        with psycopg.connect(dsn,autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                conn.execute('''CREATE TABLE bob_android_list_images (
                    batch_id text PRIMARY KEY,token_hash text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    payload jsonb NOT NULL)''')
                sample=[(A,batch('1',shared,now)),
                        (A,batch('2',shared,now)),
                        (B,batch('3',shared,now))]
                for scope,p in sample:
                    conn.execute('''INSERT INTO bob_android_list_images
                        (batch_id,token_hash,payload) VALUES(%s,%s,%s)''',
                        (p['batchId'],scope,Jsonb(p)))
                before=conn.execute('''SELECT batch_id,token_hash,payload
                    FROM bob_android_list_images ORDER BY batch_id''').fetchall()
                with patch.object(shadow,'_cache',None),patch.object(shadow,'_cache_at',0):
                    with conn.transaction():
                        conn.execute('SET TRANSACTION READ ONLY')
                        result=shadow.report(conn,now=time.time())
                self.assertEqual(result['status'],'verified-in-memory')
                self.assertEqual(result['repeatedImageReferences'],1)
                self.assertEqual(result['deviceScopeCount'],2)
                self.assertFalse(result['migrationAuthorized'])
                self.assertEqual(conn.execute('''SELECT batch_id,token_hash,payload
                    FROM bob_android_list_images ORDER BY batch_id''').fetchall(),before)
                self.assertNotIn(shared[:50],json.dumps(result))
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def test_missing_table_is_not_observed(self):
        import psycopg
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        schema='shadow_empty_'+uuid.uuid4().hex
        with psycopg.connect(dsn,autocommit=True) as conn:
            conn.execute('CREATE SCHEMA '+schema)
            try:
                conn.execute('SET search_path TO '+schema)
                with patch.object(shadow,'_cache',None),patch.object(shadow,'_cache_at',0):
                    self.assertEqual(shadow.report(conn)['status'],'not-observed')
            finally:
                conn.execute('DROP SCHEMA '+schema+' CASCADE')


if __name__ == '__main__':
    unittest.main()
