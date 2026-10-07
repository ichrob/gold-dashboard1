import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
import stop_target_audit as s

class StopTargetTests(unittest.TestCase):
 def setUp(self):
  self.start=datetime(2026,10,7,12,tzinfo=timezone.utc)
  self.end=self.start+timedelta(hours=4)
  self.plan=dict(kind='candidate',direction='LONG',entry=100,stop=95,target=110,unit='USD/oz')
 def run_case(self, prices, now_seconds=None, plan=None):
  points=[(self.start+timedelta(seconds=t),p) for t,p in prices]
  now=self.start+timedelta(seconds=now_seconds if now_seconds is not None else prices[-1][0])
  return s.evaluate(plan or self.plan,self.start,self.end,points,now)
 def test_first_observed_target_is_final_even_if_stop_later(self):
  r=self.run_case([(30,101),(60,110),(90,94)])
  self.assertEqual(r['status'],'observed-target');self.assertEqual(r['observedPrice'],110)
  self.assertTrue(r['complete']);self.assertFalse(r['productReturnKnown'])
 def test_stop_first_long_and_short(self):
  self.assertEqual(self.run_case([(30,95),(60,111)])['status'],'observed-stop')
  p={**self.plan,'direction':'SHORT','stop':105,'target':90}
  self.assertEqual(self.run_case([(30,90),(60,106)],plan=p)['status'],'observed-target')
  self.assertEqual(self.run_case([(30,105),(60,89)],plan=p)['status'],'observed-stop')
 def test_gap_does_not_turn_into_claimed_win(self):
  r=self.run_case([(30,101),(150,110)])
  self.assertEqual(r['status'],'inconclusive');self.assertEqual(r['firstObserved'],'target')
 def test_open_and_expired_without_hit(self):
  self.assertEqual(self.run_case([(30,100)])['status'],'pending')
  prices=[(t,100) for t in range(30,14401,30)]
  self.assertEqual(self.run_case(prices,14400)['status'],'no-observed-hit')
  self.assertEqual(self.run_case([(30,100)],14400)['status'],'inconclusive')
 def test_future_and_preplan_quotes_are_excluded(self):
  r=self.run_case([(-30,94),(30,100),(300,110)],60)
  self.assertEqual(r['status'],'pending');self.assertEqual(r['samples'],1)
 def test_invalid_and_conflicting_quotes_not_favorable(self):
  self.assertEqual(self.run_case([(30,110)],plan={**self.plan,'stop':101})['status'],'invalid-plan')
  self.assertEqual(self.run_case([(30,100),(30,110)])['status'],'inconclusive')
 def test_register_frozen_identity_deduplicates_origins_and_refresh_clock(self):
  now=self.start.timestamp()*1000
  record=dict(plan=self.plan,recordedAt=now,barAt=now-300000,priceAt=now,marketEvaluable=True,ruleVersion='v6')
  conn=Mock();s.register(conn,'browser',record);s.register(conn,'background',{**record,'recordedAt':now+1000})
  self.assertEqual(conn.execute.call_args_list[0].args[1][0],conn.execute.call_args_list[1].args[1][0])
  s.register(conn,'changed',{**record,'plan':{**self.plan,'stop':94}})
  self.assertNotEqual(conn.execute.call_args_list[0].args[1][0],conn.execute.call_args_list[2].args[1][0])
 def test_stale_and_missing_plans_do_not_register(self):
  conn=Mock();now=self.start.timestamp()*1000
  for p in (None,self.plan):
   s.register(conn,'x',dict(plan=p,marketEvaluable=True,recordedAt=now,priceAt=now-61000))
  conn.execute.assert_not_called()
 def test_report_only_reads_saved_results(self):
  conn=Mock();conn.execute.side_effect=[Mock(fetchall=lambda:[('pending',1)]),Mock(fetchall=lambda:[])]
  with patch.object(s,'harvest') as h:r=s.report(conn,self.start,self.end)
  h.assert_not_called();self.assertEqual(r['total'],1)
  self.assertTrue(all(c.args[0].lstrip().startswith('SELECT') for c in conn.execute.call_args_list))

if __name__=='__main__':unittest.main()
