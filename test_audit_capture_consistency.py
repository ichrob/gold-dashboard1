import unittest,os,json,time
from unittest.mock import patch
import decision_audit as a

class CaptureTests(unittest.TestCase):
 def test_invalid_first_capture_cannot_block_valid_capture(self):
  now=1800000000000
  p=dict(ruleVersion=a.RULE_VERSION,direction='LONG',barAt=now-300000,price=100,priceAt=now-180001,origin='background')
  bad_key,bad=a.normalize(p,now)
  good_key,good=a.normalize(dict(p,priceAt=now),now+1000)
  self.assertNotEqual(bad_key,good_key)
  self.assertEqual(bad['startEvidenceStatus'],'stale-time')
  self.assertEqual(good['startEvidenceStatus'],'valid')
  self.assertEqual(good_key,a.normalize(dict(p,priceAt=now),now+2000)[0])
  truth={'price':101,'at':good['recordedAt']+900000}
  result=a.summarize([(bad,[None,None,None]),(good,[truth,None,None])],now+1000000)
  self.assertEqual(result['metrics']['15']['evaluated'],1)
  self.assertFalse(bad['marketEvaluable'])

 def test_harvest_bounds_expensive_quote_ranges_to_available_pairs(self):
  from unittest.mock import Mock
  conn=Mock();a._harvest_at=0
  with patch('decision_audit.time.time',return_value=100):a.harvest(conn)
  query,params=conn.execute.call_args.args
  self.assertIn('WITH candidates AS MATERIALIZED',query)
  self.assertIn('EXISTS (SELECT 1 FROM bob_spot_observations available',query)
  self.assertIn('LIMIT %s',query)
  self.assertEqual(params,(a.HARVEST_BATCH_LIMIT,))

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class HarvestTests(unittest.TestCase):
 def test_exact_frozen_time_with_delayed_insert(self):
  import psycopg,uuid
  from psycopg import sql
  schema='capture_'+uuid.uuid4().hex
  with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
   conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
   conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
   try:
    conn.execute('CREATE TABLE bob_decision_audit(id TEXT PRIMARY KEY,recorded_at TIMESTAMPTZ,payload JSONB)')
    conn.execute('CREATE TABLE bob_decision_outcomes(decision_id TEXT,horizon INTEGER,truth JSONB,PRIMARY KEY(decision_id,horizon))')
    conn.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
    start=int(time.time()*1000)-3600000
    record=dict(recordedAt=start,marketEvaluable=True,price=100,direction='LONG')
    conn.execute("INSERT INTO bob_decision_audit VALUES('sample',to_timestamp(%s/1000.0),%s::jsonb)",(start+20000,json.dumps(record)))
    conn.execute("INSERT INTO bob_spot_observations VALUES('gold-api-xau-usd-v1',to_timestamp(%s/1000.0),101)",(start+900000,))
    a._harvest_at=0;a.harvest(conn)
    truth=conn.execute("SELECT truth FROM bob_decision_outcomes WHERE decision_id='sample' AND horizon=15").fetchone()[0]
    self.assertAlmostEqual(a.outcome(record,truth,15)['directionalPct'],1)
    self.assertEqual(conn.execute("SELECT payload FROM bob_decision_audit WHERE id='sample'").fetchone()[0],record)
   finally:
    conn.rollback();conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
