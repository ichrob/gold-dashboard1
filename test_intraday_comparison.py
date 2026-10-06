import unittest
from unittest.mock import Mock,patch
import intraday_comparison as c

class ComparisonTests(unittest.TestCase):
 def market(self,now=None):
  now=c.START if now is None else now
  return dict(ready=True,priceFresh=True,ruleVersion=c.POLICY,price=100,dataAt=now,analysisBarAt=now-300000,direction='LONG',shadowDirection='NEUTRAL')
 def row(self,slot,price=101,**kwargs):
  r=c.observation({**self.market(slot),**kwargs},slot)
  return r,dict(price=price,at=slot+c.HOUR,low=99,high=102,minutes=60)
 def test_window_and_weekend(self):
  self.assertFalse(c.active(c.START-1));self.assertTrue(c.active(c.START));self.assertFalse(c.active(c.END+c.HOUR))
  self.assertIsNone(c.observation(self.market(),c.START+300000))
  self.assertFalse(c.eligible(c.END));self.assertFalse(c.eligible(c.END-c.HOUR)) # Saturday
 def test_invalid_and_wrong_policy_are_missing_not_losses(self):
  for changes in ({'priceFresh':False},{'ready':False},{'ruleVersion':'old'},{'price':float('nan')},{'dataAt':c.START-60001},{'analysisBarAt':c.START+1}):
   r=c.observation({**self.market(),**changes},c.START)
   self.assertFalse(r['valid'])
   s=c.summarize([(r,None)],c.START+c.HOUR)
   self.assertEqual(s['evaluated'],0);self.assertEqual(s['variants']['fast']['losses'],0)
 def test_paired_wait_and_missed_chance(self):
  s=c.summarize([self.row(c.START)],c.START+c.HOUR)
  self.assertEqual(s['evaluated'],1);self.assertEqual(s['variants']['fast']['wins'],1)
  self.assertEqual(s['variants']['cautious']['wait'],1);self.assertEqual(s['missedFavorable'],1)
  self.assertAlmostEqual(s['variants']['fast']['meanPct'],1);self.assertEqual(s['leader'],'schnell')
  self.assertFalse(s['sufficient'])
 def test_unfavorable_and_short(self):
  s=c.summarize([self.row(c.START,99),self.row(c.START+c.HOUR,99,direction='SHORT',shadowDirection='SHORT')],c.START+2*c.HOUR)
  self.assertEqual(s['avoidedUnfavorable'],1);self.assertEqual(s['variants']['fast']['wins'],1)
  self.assertEqual(s['variants']['fast']['losses'],1);self.assertEqual(s['leader'],'vorsichtig')
 def test_missing_future_cannot_count_as_zero(self):
  r,t=self.row(c.START);t['at']+=60001
  s=c.summarize([(r,t)],c.START+2*c.HOUR)
  self.assertEqual(s['evaluated'],0);self.assertIsNone(s['variants']['fast']['meanPct'])
 def test_missing_ticks_do_not_fake_excursion(self):
  r,t=self.row(c.START);t['minutes']=10
  s=c.summarize([(r,t)],c.START+c.HOUR)
  self.assertEqual(s['evaluated'],1);self.assertIsNone(s['variants']['fast']['meanAdversePct'])
 def test_fixed_window_and_no_duplicates(self):
  rows=[self.row(s) for s in range(c.START,c.END,c.HOUR) if c.eligible(s)]
  s=c.summarize(rows+rows,c.END+60001)
  self.assertEqual(s['evaluated'],len(rows));self.assertEqual(s['coveragePct'],100)
  self.assertTrue(s['sufficient']);self.assertEqual(s['status'],'abgeschlossen')
  self.assertEqual(c.summarize([],c.START-1)['status'],'geplant')
 def test_capture_idempotent_sql_and_outcome_harvest(self):
  db=Mock();c.capture(db,self.market(),c.START)
  self.assertIn('ON CONFLICT DO NOTHING',db.execute.call_args_list[0].args[0])
  self.assertIn('UPDATE bob_intraday_comparison',db.execute.call_args_list[1].args[0])

if __name__=='__main__':unittest.main()
