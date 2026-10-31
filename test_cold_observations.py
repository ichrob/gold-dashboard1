import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import patch
import cold_observations as cold
from test_cold_metrics import Drive

class ReferenceTests(unittest.TestCase):
    def test_hot_and_invalid_references(self):
        hot={'evidence':{'original':1},'at':100}
        self.assertIs(cold.resolve(None,hot),hot)
        for payload in ({cold.TAG:'bad'},{cold.TAG:'a'*64,'evidence':None}):
            with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.resolve(None,payload)
    def test_content_hash_verified(self):
        value={'number':9007199254740993,'nested':[False,None,3.25]}
        key=cold.codec.digest(cold.codec.encoded(value))
        self.assertEqual(cold.resolve(None,{cold.TAG:key,'at':10},verified={key:value}),{'at':10,'evidence':value})
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):
            cold.resolve(None,{cold.TAG:key},verified={key:{'wrong':1}})

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.c=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'],autocommit=True)
        self.schema='cold_observations_'+uuid.uuid4().hex
        self.c.execute('CREATE SCHEMA '+self.schema);self.c.execute('SET search_path TO '+self.schema)
        self.c.execute('''CREATE TABLE bob_improvement_observations(campaign text,slot bigint,day text,
            valid boolean,payload jsonb,PRIMARY KEY(campaign,slot))''')
        cold.init(self.c);cold.codec._CACHE.clear();self.drive=Drive()
        self.payload={'at':123,'price':2000.5,'priceAt':122,'valid':True,'ready':False,'direction':'LONG',
            'cohort':'original','evidence':{'large':[hashlib.sha256(str(i).encode()).hexdigest() for i in range(100)],
            'originalInteger':9007199254740993}}
        self.put(1000);self.put(2000)
    def put(self,slot,payload=None):
        self.c.execute('INSERT INTO bob_improvement_observations VALUES(%s,%s,%s,TRUE,%s::jsonb)',
            ('campaign',slot,'2026-10-01',json.dumps(self.payload if payload is None else payload)))
    def tearDown(self):
        self.c.execute('DROP SCHEMA '+self.schema+' CASCADE');self.c.close()
    def read(self,slot):
        p=self.c.execute('SELECT payload FROM bob_improvement_observations WHERE slot=%s',(slot,)).fetchone()[0]
        return cold.resolve(self.c,p,drive=self.drive)
    def sql_projection(self):
        return self.c.execute("SELECT slot,payload-'evidence'-%s FROM bob_improvement_observations ORDER BY slot",(cold.TAG,)).fetchall()
    def test_lossless_dedup_reuse_and_sql_projection(self):
        before=self.sql_projection()
        first=cold.offload_batch(self.c,self.drive,now=200000000)
        self.assertEqual(first['movedRows'],2);self.assertEqual(first['newUniqueObjects'],1)
        self.assertEqual(before,self.sql_projection())
        cold.codec._CACHE.clear()
        self.assertEqual(self.read(1000),self.payload);self.assertEqual(self.read(2000),self.payload)
        self.put(3000);second=cold.offload_batch(self.c,self.drive,now=200000000)
        self.assertEqual(second['newUniqueObjects'],0);self.assertEqual(second['reusedUniqueObjects'],1)
        self.assertEqual(cold.status(self.c)['offloadedRows'],3)
        self.assertEqual(cold.status(self.c)['uniqueObjects'],1)
        self.assertEqual(self.read(3000),self.payload)
    def test_corruption_preserves_originals(self):
        self.drive.corrupt=True
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):cold.offload_batch(self.c,self.drive,now=200000000)
        self.assertEqual(self.read(1000),self.payload)
        self.assertEqual(cold.status(self.c)['uniqueObjects'],0)
    def test_concurrent_update_and_transaction_rollback(self):
        self.drive.on_upload=lambda:self.c.execute("UPDATE bob_improvement_observations SET payload='{}' WHERE slot=1000")
        self.assertEqual(cold.offload_batch(self.c,self.drive,now=200000000)['movedRows'],1)
        self.assertEqual(self.read(1000),{})
        self.put(3000)
        with patch.object(cold,'resolve',side_effect=RuntimeError('verify failure')):
            with self.assertRaises(RuntimeError):cold.offload_batch(self.c,self.drive,now=200000000)
        self.assertEqual(self.read(3000),self.payload)
        self.assertEqual(cold.status(self.c)['offloadedRows'],1)
    def test_hot_small_and_missing_evidence_untouched(self):
        self.put(199999999);self.put(3000,{'evidence':None});self.put(4000,{'at':10})
        self.assertEqual(cold.offload_batch(self.c,self.drive,now=200000000)['movedRows'],2)
        self.assertEqual(self.read(199999999),self.payload)
        self.assertEqual(self.read(3000),{'evidence':None});self.assertEqual(self.read(4000),{'at':10})
    def test_pages_skip_small_rows_and_continue_without_starving_eligible_rows(self):
        self.c.execute('DELETE FROM bob_improvement_observations')
        for i in range(100):self.put(i,{'evidence':None})
        self.put(1000)
        first=cold.offload_batch(self.c,self.drive,now=200000000)
        self.assertEqual(first['movedRows'],0);self.assertEqual(first['scannedRows'],100)
        second=cold.offload_batch(self.c,self.drive,now=200000000)
        self.assertEqual(second['movedRows'],1)
        self.assertEqual(self.read(1000),self.payload)
        self.assertEqual(cold.offload_batch(self.c,self.drive,now=200000000)['status'],'sweep-completed')
        self.assertIsNone(self.c.execute('SELECT * FROM bob_cold_observation_scan').fetchone())

    def test_corrupt_read_is_explicit(self):
        cold.offload_batch(self.c,self.drive,now=200000000)
        cold.codec._CACHE.clear();self.drive.corrupt=True
        with self.assertRaises(cold.codec.ColdArchiveUnavailable):self.read(1000)
