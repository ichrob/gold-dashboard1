import copy
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import future_analysis as a

NOW=datetime(2026,10,1,12,tzinfo=timezone.utc)
T=int(NOW.timestamp())
def payload():
 return {'chart':{'result':[{'meta':dict(symbol=a.SYMBOL,instrumentType='FUTURE',currency='USD',exchangeName='CMX',shortName='Gold Dec 26',dataGranularity='5m',regularMarketTime=T), 'timestamp':[T-600,T-300,T], 'indicators':{'quote':[dict(open=[100]*3,high=[102]*3,low=[99]*3,close=[101]*3)]}}]}}
def rows(n,step):
 return [dict(t=T-(n-i)*step,open=100+i*.1,high=101+i*.1,low=99+i*.1,close=100+i*.1) for i in range(n)]
class HistoryTests(unittest.TestCase):
 def test_reference_keeps_original_market_time_and_exact_identity(self):
  p=payload();p['chart']['result'][0]['meta']['regularMarketPrice']=4215.3
  with patch.object(a,'fetch_chart',return_value=p):
   result=a.fetch_reference(NOW)
  self.assertEqual(result['underlyingAt'],NOW.isoformat())
  self.assertEqual(result['underlyingPriceUsd'],4215.3)
  self.assertFalse(result['eligible']);self.assertFalse(result['isExchangeRealtime'])
  for key,value in [('symbol','GC=F'),('shortName','Gold Feb 27'),('regularMarketPrice',True),('regularMarketPrice',0),('regularMarketTime',T-1801),('regularMarketTime',T+1)]:
   bad=copy.deepcopy(p);bad['chart']['result'][0]['meta'][key]=value
   with self.subTest(key=key,value=value),patch.object(a,'fetch_chart',return_value=bad):
    with self.assertRaises(ValueError):a.fetch_reference(NOW)
 def test_provider_failure_status_is_safe_and_specific(self):
  secret='upstream-private-response'
  error=HTTPError('https://example.invalid/'+secret,429,secret,{},None)
  self.assertEqual(a.history_error(error),'GCZ26-Historie: Datenanbieter antwortet mit HTTP 429')
  for exc in (URLError(secret),ValueError(secret),KeyError(secret)):
   self.assertNotIn(secret,a.history_error(exc))
  self.assertEqual(a.history_error(ValueError('Doppelte Futures-Kerzen')),'Doppelte Futures-Kerzen')
 def test_exact_contract_and_closed_bars(self):
  p=payload();r,t=a.parse_chart(p,5,NOW);self.assertEqual(len(r),2)
  for key,val in [('symbol','GC=F'),('currency','EUR'),('instrumentType','CFD'),('shortName','Gold Feb 27'),('regularMarketTime',T-1801)]:
   bad=copy.deepcopy(p);bad['chart']['result'][0]['meta'][key]=val
   with self.assertRaises(ValueError):a.parse_chart(bad,5,NOW)
 def test_no_fabricated_aggregate_candles(self):
  r=rows(12,300);self.assertEqual(len(a.aggregate(r,5,15)),4)
  del r[1];self.assertEqual(len(a.aggregate(r,5,15)),3)
 def test_insufficient_or_stale_history_blocks_direction(self):
  out=a.analyse(rows(300,300),rows(300,3600),T,NOW)
  self.assertFalse(out['available']);self.assertEqual(out['direction'],'NEUTRAL')
  self.assertFalse(out['frames']['15m']['available']);self.assertEqual(out['technicalSourceFamilies'],1)
  self.assertFalse(a.frame(rows(220,300),5,NOW+timedelta(hours=2))['available'])
 def test_all_four_frames_and_expiry(self):
  out=a.analyse(rows(900,300),rows(900,3600),T,NOW)
  self.assertTrue(out['available']);self.assertEqual(set(out['frames']),{'5m','15m','1h','4h'})
  self.assertEqual(out['direction'],'NEUTRAL') # monotonic RSI overbought, no invented long
  with patch.object(a,'_state',out):
   self.assertFalse(a.current(NOW+timedelta(seconds=181))['available'])
