import copy
import json
import unittest
from unittest.mock import patch
import technical_candles as tc
import server

class CandleTests(unittest.TestCase):
    now=1791277200
    def payload(self):
        return {'symbol':'XAUUSD','interval':'5m','bars':[
            {'openTime':'2026-10-06T08:55:00Z','open':4100,'high':4102,'low':4099,'close':4101,'isOpen':False}]}

    def test_minute_native_history_and_no_fabricated_fallback(self):
        p=self.payload();p['interval']='1m';p['bars'][0]['openTime']='2026-10-06T08:59:00Z'
        rows=tc.normalize(p,'1m',self.now)
        self.assertEqual(len(rows),1)
        with patch.object(tc,'fetch',return_value=[]),patch.dict(server._technical_history,{},clear=True),patch.object(server,'fetch_json') as fallback:
            self.assertEqual(server.fetch_technical_history('1m','1d'),[])
            fallback.assert_not_called()

    def test_strict_identity_and_candle_validation(self):
        p=self.payload()
        self.assertEqual(len(tc.normalize(p,'5m',self.now)),1)
        for key,value in [('symbol','GC=F'),('interval','1h')]:
            q=copy.deepcopy(p);q[key]=value
            self.assertEqual(tc.normalize(q,'5m',self.now),[])
        for key,value in [('openTime','2026-10-06T08:55:00'),('openTime','2026-10-06T08:55:01Z'),('openTime','2026-10-06T09:05:00Z'),('high',4090),('close',float('inf')),('open',True),('isOpen',None)]:
            q=copy.deepcopy(p);q['bars'][0][key]=value
            self.assertEqual(tc.normalize(q,'5m',self.now),[],(key,value))
        p['bars']*=2
        self.assertEqual(tc.normalize(p,'5m',self.now),[])

    def test_upstream_open_cannot_be_promoted_by_local_clock(self):
        p=self.payload();p['bars'][0]['isOpen']=True
        rows=tc.normalize(p,'5m',self.now)
        with patch.object(server.time,'time',return_value=self.now):
            server.mark_bar_state(rows,5)
            self.assertTrue(rows[0]['isOpen'])
            self.assertFalse(server.technical_history_fresh(rows,5))

    def test_cache_limits_requests_and_preserves_original_clock_on_failure(self):
        with patch.dict(tc._cache,{},clear=True),patch.object(tc.time,'time',return_value=self.now),patch.object(server,'fetch_json',return_value=self.payload()) as fetch:
            a=tc.fetch('5m',fetch);tc.fetch('5m',fetch)
            self.assertEqual(fetch.call_count,1)
            with patch.object(tc.time,'time',return_value=self.now+61):
                fetch.side_effect=OSError('offline');b=tc.fetch('5m',fetch)
                self.assertEqual(a,b)
                b[0]['close']=1
                self.assertEqual(tc.fetch('5m',fetch),a)

    def test_minute_refreshes_after_thirty_seconds_without_retiming(self):
        p=self.payload();p['interval']='1m';p['bars'][0]['openTime']='2026-10-06T08:59:00Z'
        with patch.dict(tc._cache,{},clear=True),patch.object(tc.time,'time',return_value=self.now),patch.object(server,'fetch_json',return_value=p) as fetch:
            first=tc.fetch('1m',fetch)
            with patch.object(tc.time,'time',return_value=self.now+29):tc.fetch('1m',fetch)
            self.assertEqual(fetch.call_count,1)
            with patch.object(tc.time,'time',return_value=self.now+30):second=tc.fetch('1m',fetch)
            self.assertEqual(fetch.call_count,2)
            self.assertEqual(first,second)

    def test_independent_fresh_history_does_not_call_legacy(self):
        with patch.object(server.time,'time',return_value=self.now),patch.dict(server._technical_history,{},clear=True),patch.object(tc,'fetch',return_value=tc.normalize(self.payload(),'5m',self.now)),patch.object(server,'fetch_json') as legacy:
            rows=server.fetch_technical_history('5m','5d')
            self.assertEqual(rows[0]['instrument'],'XAU/USD')
            legacy.assert_not_called()

if __name__=='__main__':unittest.main()
