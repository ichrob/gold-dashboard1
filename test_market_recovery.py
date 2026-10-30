import unittest
from concurrent.futures import Future
from unittest.mock import patch
import market_recovery as m

class MarketRecoveryTests(unittest.TestCase):
 def setUp(self):
  for name in ('_PENDING','_STATE','_NEXT'):
   p=patch.object(m,name,{});p.start();self.addCleanup(p.stop)
  p=patch('background_push.gold_weekend_seconds_remaining',return_value=0);p.start();self.addCleanup(p.stop)
 def test_failure_isolation_dedup_retry_and_recovery(self):
  first,second,third=Future(),Future(),Future()
  with patch.object(m._POOL,'submit',side_effect=[first,second,third]) as submit:
   probes={'spot':lambda:None,'fx':lambda:None}
   m.tick(0,probes);m.tick(10,probes)
   self.assertEqual(submit.call_count,2)
   first.set_exception(ValueError('private details'))
   m.tick(11,probes)
   self.assertEqual(m.health()['inputs']['spot']['state'],'retrying')
   self.assertNotIn('private',str(m.health()))
   m.tick(40,probes);self.assertEqual(submit.call_count,2)
   m.tick(41,probes);self.assertEqual(submit.call_count,3)
   third.set_result({'at':'original'})
   m.tick(42,probes)
   self.assertEqual(m.health()['inputs']['spot']['state'],'call-completed')
   self.assertIn('fx',m.health()['checking'])
 def test_closed_market_no_calls(self):
  with patch('background_push.gold_weekend_seconds_remaining',return_value=60),patch.object(m._POOL,'submit') as submit:
   m.tick(0,{'spot':lambda:None});submit.assert_not_called()
 def test_all_adapters_registered(self):
  self.assertEqual(set(m.operations()),{'spot','spot-backup','fx','fx-backup','cfd','future','history-1m','history-5m','history-15m','history-30m','history-1h','history-4h'} | {'standby-'+tf for tf in ('1m','5m','15m','30m','1h','4h')})
  with patch('server.fetch_technical_history',return_value=['source']) as history:
   self.assertEqual(m.operations()['history-30m'](),['source'])
   history.assert_called_once_with('30m','1mo')
