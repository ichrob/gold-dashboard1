import json,os,time,unittest
import model_gap_review as model

class ModelTests(unittest.TestCase):
    def test_bracket_only_and_provenance(self):
        at=1700000000000
        result=model.interpolate(at,[(at-60000,2000),(at+60000,2002)])
        self.assertEqual(result['price'],2001)
        self.assertEqual(result['kind'],'interpolated')
        self.assertEqual(result['inputs'][0]['at'],at-60000)
        self.assertIsNone(result['uncertaintyBound'])
        self.assertIsNone(model.interpolate(at,[(at-1000,2000)]))
        self.assertIsNone(model.interpolate(at,[(at-200000,2000),(at+200000,2002)]))
        self.assertIsNone(model.interpolate(at,[(at,2000),(at,2001)]))
    def test_separate_return_not_product_or_training_truth(self):
        at=1700000000000
        start=model.interpolate(at,[(at,2000)])
        end=model.interpolate(at+900000,[(at+900000,2020)])
        record={'direction':'SHORT','marketEvaluable':False}
        result=model.estimate(record,15,start,end,at+1000000)
        self.assertAlmostEqual(result['directionalMovePct'],-1)
        self.assertFalse(result['usedForLearning'])
        self.assertFalse(result['originalEvidenceComplete'])
        self.assertIsNone(result['productReturnPct'])
        self.assertFalse(record['marketEvaluable'])

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI')
class StorageTests(unittest.TestCase):
    def test_model_frozen_later_original_compared_without_repair(self):
        import psycopg
        schema='gap_test_'+str(time.time_ns());dsn=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn) as c:
            c.execute('CREATE SCHEMA '+schema)
            try:
                c.execute('SET search_path TO '+schema)
                c.execute('CREATE TABLE bob_test_repairs(id text,ref jsonb,kind text,status text)')
                c.execute('CREATE TABLE bob_decision_audit(id text,payload jsonb)')
                c.execute('CREATE TABLE bob_spot_observations(stream text,quote_at timestamptz,price double precision)')
                model.init(c)
                at=1700000000000;target=at+900000;now=at+1000000
                record={'recordedAt':at,'direction':'LONG','marketEvaluable':False}
                c.execute("INSERT INTO bob_decision_audit VALUES('d',%s::jsonb)",(json.dumps(record),))
                c.execute("INSERT INTO bob_test_repairs VALUES('r',%s::jsonb,'signal','escalated')",(json.dumps({'decision':'d','horizon':15}),))
                for t,p in [(at-60000,2000),(at+60000,2002),(target-60000,2010),(target+60000,2012)]:
                    c.execute('INSERT INTO bob_spot_observations VALUES(%s,to_timestamp(%s/1000.0),%s)',(model.STREAM,t,p))
                model.tick(c,now)
                first=model.report(c)['items'][0]
                self.assertEqual(first['start']['price'],2001)
                c.execute('INSERT INTO bob_spot_observations VALUES(%s,to_timestamp(%s/1000.0),2003)',(model.STREAM,at))
                model.tick(c,now+3600001)
                later=model.report(c)['items'][0]
                self.assertEqual(later['start'],first['start'])
                self.assertEqual(later['validation']['start']['error'],-2)
                self.assertEqual(c.execute('SELECT payload FROM bob_decision_audit').fetchone()[0],record)
                self.assertEqual(c.execute('SELECT status FROM bob_test_repairs').fetchone()[0],'escalated')
            finally:c.execute('DROP SCHEMA '+schema+' CASCADE')
