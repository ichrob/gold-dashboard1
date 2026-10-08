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
 def test_reference_and_history_share_fetch_and_original_times(self):
  p=payload();p['chart']['result'][0]['meta']['regularMarketPrice']=4215.3
  with patch.object(a,'_chart_cache',{}),patch.object(a,'_chart_retry',{}),patch.object(a,'_chart_failures',{}),patch.object(a.time,'monotonic',return_value=100),patch.object(a,'_fetch_chart',return_value=p) as fetch:
   a.fetch_reference(NOW)
   chart=a.fetch_chart('5m','5d')
   fetch.assert_called_once_with('5m','5d')
   chart['chart']['result'][0]['meta']['regularMarketTime']=T+1
   self.assertEqual(a.fetch_chart('5m','5d')['chart']['result'][0]['meta']['regularMarketTime'],T)
 def test_shared_rate_limit_backoff_cannot_be_bypassed(self):
  e=HTTPError('https://example.invalid',429,'limited',{'Retry-After':'1200'},None)
  with patch.object(a,'_chart_cache',{}),patch.object(a,'_chart_retry',{}),patch.object(a,'_chart_failures',{}),patch.object(a.time,'monotonic',return_value=100),patch.object(a,'_fetch_chart',side_effect=e) as fetch:
   with self.assertRaises(HTTPError):a.fetch_chart('5m','5d')
   with self.assertRaises(URLError):a.fetch_reference(NOW)
   fetch.assert_called_once()
   self.assertEqual(a._chart_retry[('5m','5d')],1300)
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
  out=a.analyse(rows(297,300),rows(300,3600),T,NOW)
  self.assertFalse(out['available']);self.assertEqual(out['direction'],'NEUTRAL')
  self.assertFalse(out['frames']['15m']['available']);self.assertEqual(out['technicalSourceFamilies'],1)
  self.assertFalse(a.frame(rows(220,300),5,NOW+timedelta(hours=2))['available'])
 def test_all_four_frames_and_expiry(self):
  out=a.analyse(rows(900,300),rows(900,3600),T,NOW)
  self.assertTrue(out['available']);self.assertEqual(set(out['frames']),{'5m','15m','1h','4h'})
  self.assertEqual(out['direction'],'LONG') # RSI extreme no longer vetoes aligned trend and MACD
  with patch.object(a,'_state',out):
   self.assertFalse(a.current(NOW+timedelta(seconds=181))['available'])

class IntradayPolicyTests(unittest.TestCase):
 def test_four_hour_context_does_not_veto(self):
  def fake_frame(rows,minutes,now):
   return dict(available=minutes!=240,direction='LONG' if minutes!=240 else 'SHORT',trend='LONG',momentum='LONG',expiresAt=(NOW+timedelta(hours=1)).isoformat())
  with patch.object(a,'frame',side_effect=fake_frame):
   result=a.analyse(rows(900,300),rows(300,3600),T,NOW)
  self.assertTrue(result['available']);self.assertEqual(result['direction'],'LONG')
 def test_missing_hour_is_context_only(self):
  def fake_frame(rows,minutes,now):
   return dict(available=minutes!=60,direction='LONG',expiresAt=(NOW+timedelta(hours=1)).isoformat())
  with patch.object(a,'frame',side_effect=fake_frame):
   result=a.analyse(rows(900,300),[],T,NOW)
  self.assertTrue(result['available']);self.assertEqual(result['direction'],'LONG')

class AuditBoundaryTests(unittest.TestCase):
 def test_frame_rejects_invalid_duplicate_future_and_recent_gap(self):
  base=rows(220,300)
  cases=[]
  for key,value in [('close',float('nan')),('low',10000),('t',T),('t',True)]:
   bad=copy.deepcopy(base);bad[-1][key]=value;cases.append(bad)
  cases.extend([base[:-2]+base[-1:],base+[base[-1]],list(reversed(base))])
  for bad in cases:
   with self.subTest(last=bad[-1]):
    self.assertFalse(a.frame(bad,5,NOW)['available'])
 def test_old_gap_recovery_and_ema200_warmup(self):
  base=rows(220,300);del base[10]
  self.assertTrue(a.frame(base,5,NOW)['available'])
  result=a.frame(rows(100,300),5,NOW)
  self.assertTrue(result['available']);self.assertIsNone(result['ema200'])
  self.assertEqual(result['atrMethod'],'Wilder14')
 def test_stale_history_cannot_describe_current_structure(self):
  out=a.analyse(rows(900,300),rows(900,3600),T,NOW+timedelta(hours=2))
  self.assertFalse(out['available'])
  self.assertEqual(out['blocks']['marketStructure'],'NEUTRAL')
  self.assertEqual(out['fibonacci']['levels'],{})
 def test_broken_origin_invalidates_fibonacci_on_both_sides(self):
  values=[105,104,100,104,106,110,108,107,106]
  base=[dict(t=T-(len(values)-i)*300,open=v,close=v,high=v+.5,low=v-.5) for i,v in enumerate(values)]
  self.assertEqual(a.structure(base)[1]['direction'],'LONG')
  broken=copy.deepcopy(base);broken[-1].update(open=98,close=98,high=98.5,low=97.5)
  self.assertEqual(a.structure(broken)[1]['direction'],'NEUTRAL')
  invert=lambda rs:[dict(t=r['t'],open=220-r['open'],close=220-r['close'],high=220-r['low'],low=220-r['high']) for r in rs]
  self.assertEqual(a.structure(invert(base))[1]['direction'],'SHORT')
  self.assertEqual(a.structure(invert(broken))[1]['direction'],'NEUTRAL')
