import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import leverage_backup as b
N=datetime(2026,10,7,10,tzinfo=timezone.utc)
T='2026-10-07T09:59:50Z'
class Tests(unittest.TestCase):
 def setUp(self):
  self.r=dict(found=True,productVerified=True,eligible=False,currency='EUR',ask=4,askAt=T,source='Onvista',metadata=dict(status=1,simpleNonQuantoTurbo=True,underlyingType='SPOT',ratio=.01))
  self.g=dict(price=4000,at=T,underlying='XAU/USD',source='Gold')
  self.fx=dict(result='success',base='USD',rates=dict(EUR=1),data_updated_at=T,effective_at=dict(EUR=T),source='live',sources=dict(EUR='live'),market_session='open')
 def test_formula_and_clocks(self):
  x=b.calculate(self.r,self.g,self.fx,N)
  self.assertEqual(x['value'],10);self.assertTrue(x['fresh']);self.assertEqual(x['at'],'2026-10-07T09:59:50+00:00')
 def test_currency_conversion(self):
  self.fx['rates']['EUR']=.9
  self.assertEqual(b.calculate(self.r,self.g,self.fx,N)['value'],9)
 def test_old_input_never_becomes_current(self):
  self.g['at']='2026-10-07T09:40:00Z'
  x=b.calculate(self.r,self.g,self.fx,N)
  self.assertFalse(x['fresh']);self.assertEqual(x['maxInputAgeSeconds'],1200)
 def test_future_requires_exact_contract(self):
  self.r['metadata'].update(underlyingType='FUTURE',contract='GCZ26')
  with self.assertRaises(ValueError):b.calculate(self.r,self.g,self.fx,N)
  self.g.update(contract='GCZ26',underlyingType='FUTURE',delayed=True)
  self.assertFalse(b.calculate(self.r,self.g,self.fx,N)['fresh'])
 def test_future_times_and_unknown_model_rejected(self):
  self.fx['effective_at']['EUR']='2026-10-07T10:01:00Z'
  with self.assertRaises(ValueError):b.calculate(self.r,self.g,self.fx,N)
  self.r['metadata']['simpleNonQuantoTurbo']=False
  with self.assertRaises(ValueError):b.calculate(self.r,self.g,self.fx,N)
 def test_fallback_and_primary_precedence(self):
  self.r.update(leverage=8,leverageAt='2026-10-07T09:40:00Z')
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=self.fx):
   x=b.apply(self.r,N)
   self.assertEqual(x['leverage'],10);self.assertTrue(x['leverageEstimated']);self.assertFalse(x['eligible'])
   self.assertEqual(x['providerLeverage']['value'],8);self.assertEqual(self.r['leverage'],8)
   self.r['leverageAt']=T
   self.assertEqual(b.apply(self.r,N)['leverage'],8)
   self.assertTrue(b.apply(self.r,N)['leverageComparison']['comparable'])
 def test_older_calculation_does_not_replace_newer_provider(self):
  self.r.update(leverage=8,leverageAt='2026-10-07T09:55:00Z');self.g['at']='2026-10-07T09:40:00Z'
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=self.fx):
   self.assertEqual(b.apply(self.r,N)['leverage'],8)
 def test_skew_and_estimated_basis(self):
  self.g['at']='2026-10-07T09:59:10Z'
  self.assertFalse(b.calculate(self.r,self.g,self.fx,N)['fresh'])
  self.g['at']=T;self.g['estimated']=True
  self.assertFalse(b.calculate(self.r,self.g,self.fx,N)['fresh'])
 def test_comparison_skips_stale_and_flags_difference(self):
  self.r.update(leverage=8,leverageAt=T)
  e=b.calculate(self.r,self.g,self.fx,N)
  self.assertTrue(b.compare(self.r,e,N)['warning'])
  self.r['leverageAt']='2026-10-07T09:59:00Z'
  self.assertFalse(b.compare(self.r,e,N)['comparable'])
  self.r.update(leverageAt=T,leverageEstimated=True)
  self.assertFalse(b.compare(self.r,e,N)['comparable'])
 def test_future_uses_displayed_cfd_and_keeps_proxy_label(self):
  self.r['metadata'].update(underlyingType='FUTURE',contract='GCZ26')
  cfd=dict(kind='cfd',price=4000,at=T,declaredContract='GCZ26',realtimeCfd=True)
  with patch('investing_card.fetch',return_value=cfd),patch('sg_quotes.market_input',return_value=self.fx):
   x=b.apply(self.r,N)
   self.assertEqual(x['leverage'],10)
   self.assertFalse(x['eligible'])
   self.assertFalse(x['leverageCalculation']['fresh'])
   self.assertTrue(x['leverageCalculation']['inputs']['basisEstimated'])
   self.assertIn('CFD',x['leverageSource'])
   cfd['declaredContract']='GCG27'
   self.assertFalse(b.apply(self.r,N)['leverageCalculation']['available'])
if __name__=='__main__':unittest.main()
