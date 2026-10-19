import unittest,os,json,time
from datetime import datetime,timezone
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

 def test_harvest_bounds_expensive_quote_ranges_behind_a_durable_cursor(self):
  from unittest.mock import Mock
  stamp=datetime.now(timezone.utc)
  conn=Mock()
  conn.execute.side_effect=[
      Mock(fetchone=lambda:(None,None)),
      Mock(fetchall=lambda:[('one',stamp),('two',stamp)]),
      Mock(),Mock()]
  self.assertEqual(a._harvest_horizon(conn,15),2)
  selection,selection_params=conn.execute.call_args_list[1].args
  insert,insert_params=conn.execute.call_args_list[2].args
  update,update_params=conn.execute.call_args_list[3].args
  self.assertIn('ORDER BY a.recorded_at,a.id LIMIT %s',selection)
  self.assertEqual(selection_params,(15,15,15,a.HARVEST_HORIZON_BATCH))
  self.assertIn('WHERE a.id=ANY(%s::text[])',insert)
  self.assertEqual(insert_params[-1],['one','two'])
  self.assertIn('SET recorded_at=%s,decision_id=%s',update)
  self.assertEqual(update_params,(stamp,'two',15))

 def test_empty_cursor_window_resets_without_scanning_quote_ranges(self):
  from unittest.mock import Mock
  stamp=datetime.now(timezone.utc)
  conn=Mock()
  conn.execute.side_effect=[Mock(fetchone=lambda:(stamp,'last')),Mock(fetchall=lambda:[]),Mock()]
  self.assertEqual(a._harvest_horizon(conn,60),0)
  selection,params=conn.execute.call_args_list[1].args
  self.assertIn('(a.recorded_at,a.id)>(%s,%s)',selection)
  self.assertEqual(params,(60,60,60,stamp,'last',a.HARVEST_HORIZON_BATCH))
  self.assertEqual(conn.execute.call_count,3)

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
    conn.execute('CREATE TABLE bob_decision_harvest_cursor(horizon INTEGER PRIMARY KEY,recorded_at TIMESTAMPTZ,decision_id TEXT,attempted_at TIMESTAMPTZ)')
    conn.execute('INSERT INTO bob_decision_harvest_cursor(horizon) SELECT unnest(%s::integer[])',(list(a.HARVEST_HORIZONS),))
    conn.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
    start=int(time.time()*1000)-3600000
    record=dict(recordedAt=start,marketEvaluable=True,price=100,direction='LONG')
    conn.execute("INSERT INTO bob_decision_audit VALUES('sample',to_timestamp(%s/1000.0),%s::jsonb)",(start+20000,json.dumps(record)))
    conn.execute("INSERT INTO bob_spot_observations VALUES('gold-api-xau-usd-v1',to_timestamp(%s/1000.0),101)",(start+900000,))
    for _ in range(3):
     a._harvest_at=0;a.harvest(conn)
    truth=conn.execute("SELECT truth FROM bob_decision_outcomes WHERE decision_id='sample' AND horizon=15").fetchone()[0]
    self.assertAlmostEqual(a.outcome(record,truth,15)['directionalPct'],1)
    self.assertEqual(conn.execute("SELECT payload FROM bob_decision_audit WHERE id='sample'").fetchone()[0],record)
   finally:
    conn.rollback();conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
