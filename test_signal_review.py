import unittest
from datetime import datetime,timedelta,timezone
import signal_review as s
import stop_target_audit as st
import decision_audit as a
class ReviewTests(unittest.TestCase):
 def record(self,d='LONG',day='2026-10-10'):
  now=datetime.fromisoformat(day+'T10:00:00+00:00').timestamp()*1000
  r=dict(direction=d,recordedAt=now,priceAt=now,price=100,marketEvaluable=True,origin='background',barAt=now-300000,trendContext={'available':True,'intact':True,'direction':d},indicators={'adx':20})
  r['reviewVariants']=s.capture(r)
  return r
 def test_frozen_filters_and_missing(self):
  r=self.record();self.assertEqual(r['reviewVariants']['trend'],'LONG');self.assertEqual(r['reviewVariants']['adx'],'NEUTRAL')
  self.assertIsNone(s.capture({'direction':'LONG'})['adx'])
 def test_validation_and_missed_winner(self):
  r=self.record(day='2026-10-20');truth=dict(at=r['recordedAt']+3600000,price=102)
  out=s.prospective([(r,(None,truth,None))],a.outcome)['phases']
  self.assertEqual(out['collection']['baseline']['cases'],0)
  self.assertEqual(out['validation']['baseline']['wins'],1)
  self.assertEqual(out['validation']['adx']['missedWin'],1)
 def test_missing_does_not_choose_next_favorable_sample(self):
  r=self.record();r2={**r,'recordedAt':r['recordedAt']+300000}
  out=s.prospective([(r,(None,None,None)),(r2,(None,{'at':r2['recordedAt']+3600000,'price':110},None))],a.outcome)
  self.assertEqual(out['phases']['collection']['baseline']['cases'],0)
 def test_short_diagnostics(self):
  r=self.record('SHORT');t={'at':r['recordedAt']+900000,'price':101}
  out=s.diagnostics([(r,(t,None,None))],a.outcome)
  self.assertEqual(out['examples'][0]['changePct'],-1.0000000000000009)
 def test_trailing_stop_checks_old_stop_first_and_never_loosens(self):
  start=datetime(2026,10,10,tzinfo=timezone.utc);end=start+timedelta(hours=4)
  for side,prices,stop,target in [('LONG',[105,107,106,102],95,110),('SHORT',[95,93,94,98],105,90)]:
   p=dict(kind='candidate',direction=side,entry=100,stop=stop,target=target,unit='USD/oz')
   pts=[(start+timedelta(seconds=30*(j+1)),v) for j,v in enumerate(prices)]
   r=st.evaluate_lifecycle(p,start,end,pts,pts[-1][0],True)
   self.assertEqual(r['status'],'observed-stop');self.assertEqual(r['stopUpdates'],2)
   self.assertAlmostEqual(r['directionalR'],.4);self.assertEqual(r['maxAdverseR'],0)
 def test_gap_is_not_a_win(self):
  start=datetime(2026,10,10,tzinfo=timezone.utc);end=start+timedelta(hours=4)
  p=dict(kind='candidate',direction='LONG',entry=100,stop=95,target=110,unit='USD/oz')
  r=st.evaluate_lifecycle(p,start,end,[(start+timedelta(seconds=200),111)],end,True)
  self.assertEqual(r['status'],'inconclusive');self.assertIsNone(r['directionalR'])
if __name__=='__main__':unittest.main()
