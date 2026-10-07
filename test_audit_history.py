import unittest,os
from datetime import datetime,timezone
from unittest.mock import Mock
import audit_history as h
import decision_audit as a

class HistoryTests(unittest.TestCase):
 def test_large_day_loads_only_requested_payload_page(self):
  at=datetime(2026,10,7,8,tzinfo=timezone.utc)
  headers=[(str(i),at,{'direction':'NEUTRAL','ruleVersion':'historic'},None) for i in range(10005)]
  page=[('10000',at,{'direction':'NEUTRAL','ruleVersion':'historic','price':4100},None)]
  conn=Mock()
  conn.execute.side_effect=[Mock(fetchone=lambda:(10005,)),Mock(fetchall=lambda:headers),
      Mock(fetchall=lambda:page),Mock(fetchall=lambda:[]),Mock(fetchall=lambda:[])]
  result=h.report(conn,{'day':'2026-10-07','offset':10000})
  self.assertEqual(result['summary']['counts']['NEUTRAL'],10005)
  self.assertEqual([r['id'] for r in result['records']],['10000'])
  self.assertFalse(result['truncated']);self.assertIsNone(result['nextOffset'])
  query,params=conn.execute.call_args_list[2].args
  self.assertIn('LIMIT 100 OFFSET %s',query);self.assertEqual(params[-1],10000)
  self.assertNotIn('a.payload',conn.execute.call_args_list[1].args[0])
  self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in conn.execute.call_args_list))
 def test_first_signal_keeps_original_plan_and_outcomes(self):
  at=datetime(2026,10,7,8,tzinfo=timezone.utc)
  header=('signal',at,{'direction':'LONG','ruleVersion':'historic'},None)
  full=('signal',at,{'direction':'LONG','ruleVersion':'historic','plan':{'stop':4090}}, {'60':{'price':4110}})
  conn=Mock();conn.execute.side_effect=[Mock(fetchone=lambda:(1,)),Mock(fetchall=lambda:[header]),
      Mock(fetchall=lambda:[full]),Mock(fetchall=lambda:[full]),Mock(fetchall=lambda:[]),Mock(fetchall=lambda:[])]
  result=h.report(conn,{'day':'2026-10-07'})
  self.assertEqual(result['summary']['firstSignals'][0]['plan'],{'stop':4090})
  self.assertEqual(result['summary']['firstSignals'][0]['outcomes']['60']['price'],4110)
 def test_zurich_day_bounds_and_dst(self):
  start,end=h.bounds('2026-10-06')
  self.assertEqual(start.isoformat(),'2026-10-05T22:00:00+00:00')
  self.assertEqual((end-start).total_seconds(),86400)
  start,end=h.bounds('2026-10-25')
  self.assertEqual((end-start).total_seconds(),90000)
  for day in (None,'2026-10-06 OR 1=1','2026-02-31'):
   with self.assertRaises(ValueError):h.bounds(day)
 def test_separate_versions_and_absence_of_plan(self):
  at=datetime(2026,10,6,8,tzinfo=timezone.utc)
  rows=[('a',at,{'direction':'LONG','ruleVersion':'old','price':100},{}),('b',at,{'direction':'LONG','ruleVersion':'new','price':101},{}),('c',at,{'direction':'NEUTRAL','ruleVersion':'new'}, {})]
  s=h.summarize(rows)
  self.assertEqual(len(s['firstSignals']),2)
  self.assertIsNone(s['firstSignals'][0]['plan'])
  self.assertEqual(s['counts'],{'LONG':2,'NEUTRAL':1})
 def test_plan_identity_tracks_levels_not_refresh_clock(self):
  now=1791288000000
  p=dict(direction='LONG',price=4100,priceAt=now,barAt=now-300000,plan=dict(kind='candidate',direction='LONG',entry=4100,stop=4090,target=4120,unit='USD/oz',at=now,secret='discard'))
  k,r=a.normalize(p,now)
  self.assertNotIn('secret',r['plan'])
  self.assertEqual(k,a.normalize({**p,'plan':{**p['plan'],'at':now+1}},now+1)[0])
  self.assertNotEqual(k,a.normalize({**p,'plan':{**p['plan'],'stop':4095}},now)[0])
 def test_date_read_dispatch_does_not_use_latest_report(self):
  from unittest.mock import patch
  with patch.object(h,'report',return_value={'day':'2026-10-06'}) as read,patch.object(a,'report') as latest:
   self.assertEqual(a.handle(None,'read',{'day':'2026-10-06'})['day'],'2026-10-06')
   latest.assert_not_called()

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'Postgres fixture unavailable')
class HistoryDatabaseTests(unittest.TestCase):
 def test_original_day_read_paginates_without_mutation(self):
  import psycopg,json,bob_market_store
  with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
   a.init(conn);bob_market_store.init(conn)
   start,end=h.bounds('2026-10-06')
   conn.execute('DELETE FROM bob_decision_audit WHERE recorded_at >= %s AND recorded_at < %s',(start,end))
   for i in range(105):
    p=dict(direction='LONG',price=4100+i,ruleVersion='historic',products=[],recordedAt=start.timestamp()*1000+i*1000)
    conn.execute('INSERT INTO bob_decision_audit(id,recorded_at,payload) VALUES(%s,%s,%s::jsonb)',('history-test-'+str(i),start,json.dumps(p)))
   r=h.report(conn,{'day':'2026-10-06'})
   self.assertEqual(r['total'],105);self.assertEqual(len(r['records']),100);self.assertEqual(r['nextOffset'],100)
   last=h.report(conn,{'day':'2026-10-06','offset':100})
   self.assertEqual(len(last['records']),5);self.assertIsNone(last['nextOffset'])
   self.assertFalse(set(x['id'] for x in r['records'])&set(x['id'] for x in last['records']))
   conn.rollback()

