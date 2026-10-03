import copy
import time
import unittest
from datetime import timedelta
from unittest.mock import patch
import future_estimate as f
import estimate_quality as quality
from test_future_estimate import NOW,reference,history,tick

def payload():
 return dict(symbol='XAU',name='Gold',currency='USD',exchangeRate=1.0,price=4164.7,updatedAt=NOW.isoformat())
def spot_history():
 return [dict(t,proxyKind='gold-api-spot',underlying='XAU/USD') for t in history()]

class SpotFutureTests(unittest.TestCase):
 def test_collected_contract_reference_is_shared_without_product_fields(self):
  newer=dict(reference(),underlyingAt=(NOW-timedelta(seconds=750)).isoformat(),
             source='Yahoo Finance · GCZ26.CMX · verzögerter Börsenkurs',sourceUrl='https://finance.yahoo.com/quote/GCZ26.CMX/')
  with patch.object(f,'_research_reference',{}),patch.object(f,'_spot_ticks',spot_history()):
   f.remember_reference(newer,NOW)
   out=f.current_estimate(reference(),NOW)
   self.assertTrue(out['available']);self.assertEqual(out['referenceAt'],newer['underlyingAt'])
   self.assertEqual(out['referenceSource'],newer['source'])
   self.assertFalse(f.current_estimate(dict(reference(),contract='GCG27'),NOW)['available'])
   self.assertFalse(f.current_estimate(reference(),NOW+timedelta(seconds=1801))['available'])
   self.assertFalse(out['eligible']);self.assertNotIn('bid',out)
 def test_disabled_provider_is_identified_before_first_observation(self):
  with patch.object(f,'_ticks',[]),patch.object(f,'_spot_ticks',[]),patch.object(f,'_source_error','Investing.com deaktiviert; ersetzt durch Gold-API.com'),patch.object(f,'_spot_source_error',None):
   result=f.current_estimate(reference(),NOW)
   self.assertEqual(result['proxyKind'],'gold-api-spot')
   legacy=next(v for v in result['alternatives'] if v['proxyKind']=='investing-cfd')
   self.assertIn('deaktiviert',legacy['sourceStatus'])
   self.assertNotIn('sourceStatus',result)
 def setUp(self):
  for module,names in [(f,('_ticks','_spot_ticks')),(quality,('_pending','_errors','_seen','_truth_receipts'))]:
   for name in names:
    p=patch.object(module,name,[] if name.endswith('ticks') else {});p.start();self.addCleanup(p.stop)
 def test_original_quote_timestamp_and_identity(self):
  t=f.parse_gold_api(payload(),NOW);self.assertEqual(t['at'],NOW.isoformat())
  for key,value in [('symbol','XAUT'),('currency','EUR'),('exchangeRate',True),('price',0),('price',float('nan')),('updatedAt',(NOW-timedelta(seconds=61)).isoformat()),('updatedAt',(NOW+timedelta(seconds=1)).isoformat()),('updatedAt','2026-10-01T07:40:30')]:
   d=payload();d[key]=value
   with self.assertRaises(ValueError):f.parse_gold_api(d,NOW)
 def test_factor_formula_exact_reference_and_no_cfd_mixing(self):
  out=f.calculate(reference(),spot_history(),NOW,'gold-api-spot')
  self.assertTrue(out['available']);self.assertEqual(out['proxySource'],'Gold-API.com · XAU/USD Spot')
  self.assertAlmostEqual(out['priceUsd'],round(4191.4*4107.9/4100,2))
  self.assertFalse(out['isExchangeRealtime']);self.assertFalse(out['eligible'])
  self.assertFalse(f.calculate(reference(),history(),NOW,'gold-api-spot')['available'])
  self.assertFalse(f.calculate(dict(reference(),contract='GCG27'),spot_history(),NOW,'gold-api-spot')['available'])
  self.assertFalse(f.calculate(reference(),spot_history()[3:],NOW,'gold-api-spot')['available'])
 def test_cached_observation_never_refreshes_and_contradictions_rejected(self):
  t=f.parse_gold_api(payload(),NOW);f.record_spot_tick(t,NOW)
  f.record_spot_tick(t,NOW+timedelta(seconds=30));self.assertEqual(len(f._spot_ticks),1)
  with self.assertRaises(ValueError):f.record_spot_tick(dict(t,price=t['price']+1),NOW)
  with self.assertRaises(ValueError):f.record_spot_tick(t,NOW+timedelta(seconds=61))
 def test_fallback_keeps_validation_separate(self):
  with patch.object(f,'_spot_ticks',spot_history()):
   result=f.current_estimate(reference(),NOW)
   self.assertTrue(result['available']);self.assertEqual(result['proxyKind'],'gold-api-spot')
   self.assertFalse(result['validation']['ready']);self.assertNotIn('comparisonErrorUsd',result)
   self.assertTrue(result['collection']['currentFresh'])
  self.assertNotEqual(f.validation_key('GCZ26','gold-api-spot'),f.validation_key('GCZ26','investing-cfd'))
 def test_collector_uses_replacement_only(self):
  class Stop(Exception):pass
  event=type('Event',(),{'wait':lambda self,seconds:(_ for _ in ()).throw(Stop())})()
  t=f.parse_gold_api(payload(),NOW)
  with patch.object(f,'_active_until',time.monotonic()+60),patch.object(f,'fetch_spot_tick',return_value=t) as spot,patch.object(f,'fetch_tick') as cfd,patch.object(f,'record_spot_tick') as record,patch.object(f.threading,'Event',return_value=event):
   with self.assertRaises(Stop):f._collect()
   spot.assert_called_once();record.assert_called_once_with(t);cfd.assert_not_called()
