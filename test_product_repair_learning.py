import unittest
from datetime import datetime,timezone
import product_repair_learning as r

NOW=1792404000000
def iso(t):return datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
def item(missing=None,t=NOW,source='comdirect'):
 return dict(isin='test',missing=missing or [],state='incomplete' if missing else 'issuer-evidence-complete',quoteSourceAt=iso(t),dataQuoteSource=source)
class LearningTests(unittest.TestCase):
 def step(self,current,previous=None,t=NOW):
  current['repairLearning']=r.update(current,previous or {},t);return current
 def test_repeated_cached_quote_does_not_confirm(self):
  broken=self.step(item(['quote-time']))
  first=self.step(item(t=NOW+30000),broken,NOW+30000)
  same=self.step(item(t=NOW+30000),first,NOW+60000)
  self.assertEqual(same['repairLearning']['status'],'verifying')
  self.assertEqual(same['repairLearning']['sourceSuccesses']['comdirect'],0)
  good=self.step(item(t=NOW+90000),same,NOW+90000)
  self.assertEqual(good['repairLearning']['sourceSuccesses']['comdirect'],1)
  again=self.step(item(t=NOW+120000),good,NOW+120000)
  self.assertEqual(again['repairLearning']['sourceSuccesses']['comdirect'],1)
 def test_recurrence_and_stale_reset_confirmation(self):
  broken=self.step(item(['quote']))
  first=self.step(item(t=NOW+30000),broken,NOW+30000)
  bad=self.step(item(['quote']),first,NOW+60000)
  self.assertEqual(bad['repairLearning']['incidents']['quotes']['checks'],0)
  stale=self.step(item(t=NOW),bad,NOW+180000)
  self.assertEqual(stale['repairLearning']['incidents']['quotes']['state'],'awaiting-evidence')
 def test_source_change_needs_two_checks(self):
  broken=self.step(item(['quote']))
  first=self.step(item(t=NOW+30000),broken,NOW+30000)
  other=self.step(item(t=NOW+60000,source='swissquote'),first,NOW+60000)
  self.assertEqual(other['repairLearning']['incidents']['quotes']['checks'],1)
 def test_exclusions_do_not_learn(self):
  for code in r.EXCLUDED:
   out=self.step(item([code,'quote']))['repairLearning']
   self.assertEqual(out['status'],'excluded');self.assertFalse(out['incidents'])
 def test_persisted_plan_restore_and_stale_disable(self):
  report=dict(status='ok',lastCheckedAt=iso(NOW),items=[dict(isin='test',repairLearning=dict(sourceSuccesses={'swissquote':3,'comdirect':1}))])
  r.install(report,NOW);self.assertEqual(r.source_order('test')[0],'swissquote')
  r.install(report,NOW+180001);self.assertEqual(r.source_order('test')[0],'comdirect')
 def test_static_terms_require_two_separated_checks(self):
  broken=self.step(item(['ratio']))
  good=item();good['fieldRecovery']={'observations':{'ratio':{'reviewedAt':iso(NOW)}}}
  first=self.step(dict(good),broken,NOW+30000)
  second=self.step(dict(good),first,NOW+60000)
  self.assertEqual(second['repairLearning']['status'],'ready')
  self.assertEqual(second['repairLearning']['sourceSuccesses']['comdirect'],0)
if __name__=='__main__':unittest.main()
