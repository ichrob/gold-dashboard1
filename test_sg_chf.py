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
  evidence=out['currencyConversion']['evidence']
  self.assertEqual(evidence['chfAt'],at)
  self.assertEqual(evidence['eurAt'],at)
  self.assertEqual(evidence['eur'],.9)
  self.assertEqual(evidence['chf'],.8)
  self.assertEqual(out['currencyConversion']['nativeAt'],at)
  for old in ('data_updated_at',):
   bad=dict(fx);bad[old]=(now-timedelta(seconds=200)).isoformat()
   self.assertNotIn('chartEvidence',convert_analysis(r,bad,now))
  fx['sources']['CHF']='cached'
  self.assertNotIn('chartEvidence',convert_analysis(r,fx,now))
 def test_ch_market_is_explicit(self):
  self.assertEqual(q.sg_market('DE000FG34XV8')[1:],('CBSW','CHF'))
  self.assertEqual(q.sg_market('DE000FG7K275')[1:],('CBDE','EUR'))
