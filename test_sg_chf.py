import unittest
from datetime import datetime,timezone,timedelta
from sg_chf import convert_analysis
import product_quotes as q
class ChfTests(unittest.TestCase):
 def test_conversion_and_original(self):
  now=datetime.now(timezone.utc);at=(now-timedelta(seconds=20)).isoformat()
  r={'chartEvidence':{'bid':36,'ask':36.01,'currency':'CHF','pointAt':at}}
  fx={'result':'success','base':'USD','market_session':'open','sources':{'EUR':'live','CHF':'live'},'rates':{'EUR':.9,'CHF':.8},'data_updated_at':at,'effective_at':{'EUR':at,'CHF':at}}
  out=convert_analysis(r,fx,now)
  self.assertEqual(out['nativeChartEvidence'],r['chartEvidence'])
  self.assertAlmostEqual(out['chartEvidence']['bid'],40.5)
  self.assertEqual(out['chartEvidence']['currency'],'EUR')
  fx['sources']['CHF']='cached'
  self.assertNotIn('chartEvidence',convert_analysis(r,fx,now))
 def test_ch_market_is_explicit(self):
  self.assertEqual(q.sg_market('DE000FG34XV8')[1:],('CBSW','CHF'))
  self.assertEqual(q.sg_market('DE000FG7K275')[1:],('CBDE','EUR'))
