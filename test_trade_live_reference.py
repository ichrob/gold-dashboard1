import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from trade_reference import align_live,lookup
class LiveReferenceTests(unittest.TestCase):
 def fixtures(self):
  raw='2026-10-14T10:00:00+00:00';at=datetime.fromisoformat(raw).timestamp()
  g={'stale':False,'data_state':{'status':'fresh'},'xau':{'currency':'USD','unit':'troy_oz'},'price_as_of':raw,'spot_usd_oz':4100}
  f={'result':'success','base':'USD','source':'live','sources':{'EUR':'live'},'market_session':'open','effective_at':{'EUR':raw},'data_updated_at':raw,'rates':{'EUR':.86}}
  return raw,at,g,f
 def test_aligned_live_preserves_source_time(self):
  r,t,g,f=self.fixtures();x=align_live(r,g,f,t+10)
  self.assertTrue(x['available']);self.assertEqual(x['goldReference'],4100);self.assertEqual(x['fxReference'],.86);self.assertEqual(x['maxSkewSeconds'],0)
 def test_stale_future_wrong_currency_rejected(self):
  r,t,g,f=self.fixtures()
  self.assertFalse(align_live(r,g,f,t+91)['available'])
  self.assertFalse(align_live(r,g,f,t-1)['available'])
  f['base']='EUR'
  with self.assertRaises(ValueError):align_live(r,g,f,t+10)
 def test_live_used_without_waiting_for_archive(self):
  r,t,g,f=self.fixtures()
  with patch('trade_reference.time.time',return_value=t+10),patch('sg_quotes.market_input',side_effect=lambda k:g if k=='spot' else f),patch('trade_reference.historical_lookup') as h:
   self.assertTrue(lookup(r)['available']);h.assert_not_called()
 def test_old_reference_never_replaced_with_current(self):
  r,t,g,f=self.fixtures()
  with patch('trade_reference.time.time',return_value=t+3600),patch('sg_quotes.market_input') as m,patch('trade_reference.historical_lookup',return_value={'available':False}):
   self.assertFalse(lookup(r)['available']);m.assert_not_called()
if __name__=='__main__':unittest.main()
