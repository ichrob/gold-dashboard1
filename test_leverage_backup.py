import unittest
import copy
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
 def test_last_original_issuer_leverage_is_weekend_reference_not_live(self):
  from datetime import timedelta
  original=copy.deepcopy(self.r)
  original.update(isin='DE000FD0S0G4',leverage=12.4,leverageAt=T,
                  source='SG',leverageEstimated=False)
  weekend=N+timedelta(days=2)
  proof=b.historical_reference(original,weekend)
  self.assertEqual(proof['value'],12.4)
  self.assertEqual(proof['kind'],'historical-issuer-leverage')
  self.assertFalse(proof['current'])
  self.assertFalse(proof['tradeApproved'])
  self.assertTrue(proof['researchOnly'])
  self.assertIsNone(b.current_evidence(original,weekend))
  for key,val in [('leverageEstimated',True),('leverageAt',None),
                  ('productVerified',False),('isin','DE000FD0S0G5')]:
   bad=dict(original,**{key:val})
   self.assertIsNone(b.historical_reference(bad,weekend))
  self.assertIsNone(b.historical_reference(original,N+timedelta(days=5)))

 def test_historical_calculation_uses_original_clocks_and_rechecked_formula(self):
  from datetime import timedelta
  original=copy.deepcopy(self.r)
  original.update(isin='DE000FD0S0G4',leverageEstimated=True)
  original['metadata']['currency']='EUR'
  original['leverageCalculation']=b.calculate(original,self.g,self.fx,N)
  at=N+timedelta(days=2)
  ref=b.historical_reference(original,at)
  self.assertEqual(ref['kind'],'historical-calculated-gearing')
  self.assertAlmostEqual(ref['value'],10)
  self.assertFalse(ref['current'])
  self.assertIsNone(b.current_evidence(original,at))
  for key,change in [('value',11),('fresh',False)]:
   bad=copy.deepcopy(original);bad['leverageCalculation'][key]=change
   self.assertIsNone(b.historical_reference(bad,at))
  bad=copy.deepcopy(original)
  bad['leverageCalculation']['inputs']['basisAt']='2026-10-07T09:40:00Z'
  self.assertIsNone(b.historical_reference(bad,at))
  bad=copy.deepcopy(original);bad['metadata']['currency']='CHF'
  self.assertIsNone(b.historical_reference(bad,at))
  bad=copy.deepcopy(original);bad['metadata']['simpleNonQuantoTurbo']=False
  self.assertIsNone(b.historical_reference(bad,at))
  bad=copy.deepcopy(original);bad['leverageCalculation']['inputs']['basisEstimated']=True
  self.assertIsNone(b.historical_reference(bad,at))
  self.assertIsNone(b.historical_reference(original,N+timedelta(days=5)))

 def test_stale_eligible_flag_does_not_hide_fresh_backup(self):
  r=copy.deepcopy(self.r)
  r.update(eligible=True,bid=3.99,bidAt='2026-10-07T09:50:00Z',askAt='2026-10-07T09:50:00Z')
  r['analysisQuote']=dict(bid=4.99,ask=5,askAt=T,bidAt=T,currency='EUR',priceKind='market-observation')
  self.assertEqual(b.select_analysis_quote(r,N)['ask'],5)
  self.assertEqual(b.calculate(r,self.g,self.fx,N)['value'],8)
  r['bidAt']=r['askAt']=T
  self.assertEqual(b.select_analysis_quote(r,N)['ask'],4)

 def test_calculated_evidence_requires_reproducible_fresh_inputs(self):
  r=copy.deepcopy(self.r)
  r['leverageCalculation']=b.calculate(r,self.g,self.fx,N)
  self.assertEqual(b.current_evidence(r,N)['value'],10)
  self.assertIsNone(b.current_evidence(r,N.replace(minute=10)))
  for key,value in [('value',11),('fresh',False)]:
   bad=copy.deepcopy(r);bad['leverageCalculation'][key]=value
   self.assertIsNone(b.current_evidence(bad,N))
  r['leverageCalculation']['inputs']['basisEstimated']=True
  self.assertIsNone(b.current_evidence(r,N))

 def test_native_chf_research_gearing_without_eur_quote(self):
  original=dict(self.r,found=False,currency='CHF',nativeChartEvidence=dict(
      bid=3.99,ask=4.0,currency='CHF',pointAt=T),metadata=dict(
      status=1,simpleNonQuantoTurbo=True,underlyingType='SPOT',ratio=.01))
  fx=dict(self.fx,rates={'CHF':.8},sources={'CHF':'live'},
          effective_at={'CHF':T})
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=fx):
   out=b.apply(original,N)
  self.assertAlmostEqual(out['leverage'],8)
  self.assertTrue(out['leverageEstimated'])
  self.assertTrue(out['leverageCalculation']['fresh'])
  self.assertEqual(out['leverageCalculation']['inputs']['quoteCurrency'],'CHF')
  self.assertEqual(out['leverageCalculation']['inputs']['askNative'],4)
  self.assertIsNone(out['leverageCalculation']['inputs']['askEur'])
  self.assertNotIn('chartEvidence',out)
  self.assertFalse(out['found'])
  self.assertFalse(out['eligible'])
  self.assertIn('keine EUR-Handelsquotierung',out['leverageNote'])
  fx['sources']['CHF']='cached'
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=fx):
   not_current=b.apply(original,N)
  self.assertFalse(not_current['leverageCalculation']['fresh'])
  self.assertFalse(not_current['eligible'])
  fx['sources']['CHF']='live'
  fx['effective_at']['CHF']='2026-10-07T09:29:59Z'
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=fx):
   too_old=b.apply(original,N)
  self.assertFalse(too_old['leverageCalculation']['available'])

 def test_unknown_and_explicit_quanto_are_distinguished(self):
  original=copy.deepcopy(self.r)
  for state, expected in (
      ('unknown', 'nicht eindeutig'),
      ('quanto', 'Quanto-Produkt'),
  ):
   with self.subTest(state=state):
    r=copy.deepcopy(original)
    r['metadata'].update(simpleNonQuantoTurbo=False, quantoState=state)
    r['issuerLeverageReference']={'value':12,'dated':False,'sourceAt':None}
    result=b.apply(r,N)
    self.assertFalse(result['leverageCalculation']['available'])
    self.assertIn(expected,result['leverageCalculation']['reason'])
    self.assertNotIn('leverage',result)
    self.assertFalse(result['eligible'])
    self.assertEqual(result['issuerLeverageReference']['value'],12)

 def test_unrelated_ko_conflicts_do_not_block_verified_non_quanto_model(self):
  r=copy.deepcopy(self.r)
  isin='DE000FG7N6Z2'
  source='https://www.comdirect.de/inf/zertifikate/'+isin
  r.update(isin=isin,direction='LONG',conditions={'quanto':{'value':False}})
  r['metadata'].update(simpleNonQuantoTurbo=False,simpleTurbo=True,quantoState='unknown',
      direction='LONG',currency='EUR',underlying='XAU/USD')
  values=dict(quanto=False,direction='LONG',currency='EUR',
              underlying='XAU/USD',ratio=.01,type='Knock-out Turbo')
  observations={key:dict(value=value,conditionVerified=True,source=source,reviewedAt=T)
                for key,value in values.items()}
  r['comdirectFieldsBackup']=dict(isin=isin,state='conflict',inactive=False,
      source=source,conflicts=['ko','strike'],observations=observations)
  reconciled=b.reconcile_model(r,N)
  self.assertTrue(reconciled['metadata']['simpleNonQuantoTurbo'])
  self.assertEqual(reconciled['metadata']['quantoState'],'non-quanto')
  self.assertFalse(reconciled['eligible'])
  blocked=copy.deepcopy(r)
  blocked['comdirectFieldsBackup']['conflicts'].append('currency')
  self.assertFalse(b.reconcile_model(blocked,N)['metadata']['simpleNonQuantoTurbo'])

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
 def test_backup_analysis_keeps_current_provider_priority(self):
  self.r.update(backupActive=True,leverage=8,leverageAt=T)
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=self.fx):
   out=b.apply(self.r,N)
   self.assertEqual(out['leverage'],8)
   self.assertEqual(out['leverageCalculation']['value'],10)
   self.assertFalse(out['eligible'])
   self.g['at']='2026-10-07T09:40:00Z'
   self.assertEqual(b.apply(self.r,N)['leverage'],8)
 def test_older_calculation_does_not_replace_newer_provider(self):
  self.r.update(leverage=8,leverageAt='2026-10-07T09:55:00Z');self.g['at']='2026-10-07T09:40:00Z'
  with patch('spot_data.current',return_value=self.g),patch('sg_quotes.market_input',return_value=self.fx):
   self.assertEqual(b.apply(self.r,N)['leverage'],8)
 def test_skew_and_estimated_basis(self):
  self.g['at']='2026-10-07T09:58:10Z'
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
 def test_comparison_log_level_matches_warning_flag(self):
  e=b.calculate(self.r,self.g,self.fx,N)
  logger=b.logging.getLogger(b.__name__)
  b._COMPARISONS.clear()
  self.r.update(leverage=10,leverageAt=T)
  with patch.object(logger,'info') as info,patch.object(logger,'warning') as warning:
   self.assertFalse(b.compare(self.r,e,N)['warning'])
  info.assert_called_once();warning.assert_not_called()
  b._COMPARISONS.clear()
  self.r['leverage']=8
  with patch.object(logger,'info') as info,patch.object(logger,'warning') as warning:
   self.assertTrue(b.compare(self.r,e,N)['warning'])
  info.assert_not_called();warning.assert_called_once()
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
 def test_analysis_tolerance_boundaries(self):
  from datetime import timedelta
  def clock(seconds):return (N-timedelta(seconds=seconds)).isoformat()
  self.g['at']=clock(300)
  self.r['askAt']=clock(210)
  self.fx.update(data_updated_at=clock(210),effective_at={'EUR':clock(210)})
  x=b.calculate(self.r,self.g,self.fx,N)
  self.assertTrue(x['inputsFresh']);self.assertEqual(x['maxAllowedSkewSeconds'],90)
  self.assertEqual(x['maxAllowedInputAgeSeconds'],300)
  self.g['at']=clock(301)
  self.assertFalse(b.calculate(self.r,self.g,self.fx,N)['inputsFresh'])
  self.g['at']=clock(299);self.r['askAt']=clock(208)
  self.assertFalse(b.calculate(self.r,self.g,self.fx,N)['inputsFresh'])
if __name__=='__main__':unittest.main()
