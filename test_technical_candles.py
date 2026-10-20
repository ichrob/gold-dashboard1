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
        with patch.object(tc,'fetch',return_value=[]),patch.dict(server._technical_history,{},clear=True),patch.dict(server._ema_backfill_attempted,{},clear=True),patch.dict(server._ema_backfill_series,{},clear=True),patch.object(server,'fetch_json',return_value={'points':[]}) as fallback:
            self.assertEqual(server.fetch_technical_history('1m','1d'),[])
            fallback.assert_called_once()
            self.assertIn('symbol=xau',fallback.call_args.args[0])

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

    def test_five_minute_refreshes_after_thirty_seconds(self):
        with patch.dict(tc._cache,{},clear=True),patch.object(tc.time,'time',return_value=self.now),patch.object(server,'fetch_json',return_value=self.payload()) as fetch:
            first=tc.fetch('5m',fetch)
            with patch.object(tc.time,'time',return_value=self.now+29):tc.fetch('5m',fetch)
            self.assertEqual(fetch.call_count,1)
            with patch.object(tc.time,'time',return_value=self.now+30):second=tc.fetch('5m',fetch)
            self.assertEqual(fetch.call_count,2)
            self.assertEqual(first,second)

    def test_15m_boundary_poll_at_most_every_30s_without_fake_close(self):
        p = self.payload()
        p['interval'] = '15m'
        p['bars'][0]['openTime'] = '2026-10-06T08:45:00Z'
        p['bars'][0]['isOpen'] = True  # Provider has not confirmed the close.
        with patch.dict(tc._cache, {}, clear=True), patch.object(server, 'fetch_json', return_value=p) as upstream:
            def check(offset):
                with patch.object(tc.time, 'time', return_value=self.now + offset):
                    return tc.fetch('15m', upstream)
            first = check(0)
            self.assertEqual(upstream.call_count, 1)
            self.assertTrue(first[0]['isOpen'])
            self.assertTrue(check(29)[0]['isOpen'])
            self.assertEqual(upstream.call_count, 1)
            self.assertTrue(check(30)[0]['isOpen'])
            self.assertEqual(upstream.call_count, 2)
            self.assertTrue(check(60)[0]['isOpen'])
            self.assertEqual(upstream.call_count, 3)
            check(90)  # Outside short boundary window; regular 60s TTL.
            self.assertEqual(upstream.call_count, 3)
            check(120)
            self.assertEqual(upstream.call_count, 4)

    def test_15m_boundary_accepts_only_provider_confirmed_close(self):
        p = self.payload()
        p['interval'] = '15m'
        p['bars'][0]['openTime'] = '2026-10-06T08:45:00Z'
        p['bars'][0]['isOpen'] = True
        with patch.dict(tc._cache, {}, clear=True), patch.object(server, 'fetch_json', return_value=p) as upstream:
            with patch.object(tc.time, 'time', return_value=self.now):
                old = tc.fetch('15m', upstream)
            self.assertTrue(old[0]['providerIsOpen'])
            self.assertTrue(old[0]['isOpen'])
            p['bars'][0]['isOpen'] = False
            with patch.object(tc.time, 'time', return_value=self.now + 30):
                accepted = tc.fetch('15m', upstream)
            self.assertEqual(upstream.call_count, 2)
            self.assertEqual(accepted[0]['openTime'], old[0]['openTime'])
            self.assertFalse(accepted[0]['isOpen'])
            self.assertFalse(accepted[0]['providerIsOpen'])

    def test_rolling_window_preserves_only_older_confirmed_candles(self):
        p = self.payload()
        old = tc.normalize(p, '5m', self.now)
        unconfirmed = dict(old[0], openTime=old[0]['openTime']-300000,
                           isOpen=True, providerIsOpen=True)
        fresh = copy.deepcopy(p)
        fresh['bars'][0]['openTime'] = '2026-10-06T09:00:00Z'
        fresh['bars'][0]['close'] = 4102
        with patch.dict(tc._cache, {'5m': (self.now-100, [unconfirmed]+old)}, clear=True), patch.object(tc.time, 'time', return_value=self.now+600):
            merged = tc.fetch('5m', lambda *a, **k: fresh)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0], old[0])
        self.assertEqual(merged[1]['close'], 4102)
        self.assertEqual(merged[1]['openTime']-merged[0]['openTime'], 300000)

    def test_fresh_correction_wins_and_gaps_are_not_filled(self):
        old = tc.normalize(self.payload(), '5m', self.now)
        fresh = self.payload()
        fresh['bars'][0]['close'] = 4102
        with patch.dict(tc._cache, {'5m': (self.now-100, old)}, clear=True), patch.object(tc.time, 'time', return_value=self.now):
            merged = tc.fetch('5m', lambda *a, **k: fresh)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['close'], 4102)

    def test_short_but_fresh_independent_history_triggers_bounded_ema_warmup(self):
        # A single fresh provider candle cannot compute EMA200. The alternate
        # XAU/USD history is checked, without ever querying a futures feed.
        with patch.object(server.time,'time',return_value=self.now),patch.dict(server._technical_history,{},clear=True),patch.dict(server._ema_backfill_attempted,{},clear=True),patch.dict(server._ema_backfill_series,{},clear=True),patch.object(tc,'fetch',return_value=tc.normalize(self.payload(),'5m',self.now)),patch.object(server,'fetch_json',return_value={'points':[]}) as history:
            rows=server.fetch_technical_history('5m','5d')
            self.assertEqual(rows[0]['instrument'],'XAU/USD')
            history.assert_called_once()
            self.assertTrue(history.call_args.args[0].startswith('https://xaus.com/api/v1/chart?'))

if __name__=='__main__':unittest.main()
