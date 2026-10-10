import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import auto_collection
import investing_card as c


class CfdBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.quote = dict(price=4171.75, at=datetime.now(timezone.utc).isoformat(),
                          realtimeCfd=True, isExchangeRealtime=False, kind='cfd')
        for name, value in (('_cached', None), ('_last_observed', None), ('_next_fetch', 0), ('_health', {'state':'starting','lastCheckedAt':None,'sourceAt':None})):
            p=patch.object(c,name,value);p.start();self.addCleanup(p.stop)

    def test_background_collection_without_browser_and_shared_fetch(self):
        with patch.object(c,'_fetch',return_value=self.quote) as source:
            c.collect_once()
            with ThreadPoolExecutor(max_workers=4) as pool:
                quotes=list(pool.map(lambda _:c.fetch(),range(8)))
            self.assertEqual(source.call_count,1)
            self.assertTrue(all(q['at']==self.quote['at'] for q in quotes))
            self.assertEqual(c.health()['state'],'current')
            quotes[0]['price']=9999
            self.assertEqual(c.fetch()['price'],4171.75)

    def test_failure_clears_current_data_and_recovers_next_cycle(self):
        with patch.object(c,'_fetch',return_value=self.quote):c.collect_once()
        with patch.object(c,'_next_fetch',0),patch.object(c,'_fetch',side_effect=OSError('offline')):
            c.collect_once()
            self.assertEqual(c.health()['state'],'unavailable')
            self.assertEqual(c.health()['sourceAt'],self.quote['at'])
            with self.assertRaises(OSError):c.fetch()
        with patch.object(c,'_next_fetch',0),patch.object(c,'_fetch',return_value=self.quote):
            c.collect_once();self.assertEqual(c.health()['state'],'current')

    def test_cached_source_never_gets_a_new_time_or_realtime_label(self):
        epoch=datetime.fromisoformat(self.quote['at']).timestamp()
        with patch.object(c,'_fetch',return_value=self.quote):c.collect_once()
        with patch.object(c.time,'time',return_value=epoch+121):
            q=c.fetch()
            self.assertFalse(q['realtimeCfd'])
            self.assertEqual(q['at'],self.quote['at'])
            self.assertEqual(c.health()['state'],'stale')

    def test_collector_repeats_without_any_browser_request(self):
        stop=threading.Event()
        cycles=[]
        def wait(seconds):
            cycles.append(seconds)
            if len(cycles)==2:stop.set()
        with patch.object(c.background_push,'gold_weekend_seconds_remaining',return_value=0),patch.object(c.background_push,'degiro_poll_seconds',return_value=30),patch.object(stop,'wait',side_effect=wait),patch.object(c,'collect_once') as collect:
            c._collect(stop)
            self.assertEqual(collect.call_count,2)
            self.assertTrue(all(1<=seconds<=30 for seconds in cycles))

    def test_start_is_independent_of_comparison_hours(self):
        with patch.object(auto_collection,'enabled',return_value=True),patch.object(auto_collection,'in_window',return_value=False),patch.object(auto_collection,'_thread',Mock(is_alive=lambda:True)),patch('future_comparison.start'),patch('spot_daily_change.start'),patch.object(c,'start') as start:
            auto_collection.start();start.assert_called_once()

    def test_poll_interval_counts_from_request_start(self):
        with patch.object(c.time,'monotonic',side_effect=[0,0,30,30]),patch.object(c,'_fetch',return_value=self.quote) as fetch:
            c.fetch();c.fetch()
            self.assertEqual(fetch.call_count,2)

    def test_old_or_conflicting_source_cannot_replace_new_observation(self):
        with patch.object(c,'_fetch',return_value=self.quote):c.fetch()
        for change in ({'at':'2026-01-01T00:00:00+00:00'}, {'price':4200}):
            with patch.object(c,'_next_fetch',0),patch.object(c,'_fetch',return_value={**self.quote,**change}):
                with self.assertRaises(ValueError):c.fetch()
                self.assertEqual(c._last_observed,self.quote)
                self.assertIsNone(c._cached)

    def test_source_request_has_cache_key_but_keeps_identity_check(self):
        response=Mock()
        response.url=c.URL+'?_bob_ts=123'
        response.read.return_value=b'fixture'
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        with patch.object(c,'urlopen',return_value=response) as request,patch.object(c,'parse',return_value=self.quote):
            c._fetch()
            self.assertIn('?_bob_ts=',request.call_args.args[0].full_url)
            response.url='https://example.com/commodities/gold?_bob_ts=123'
            with self.assertRaises(ValueError):c._fetch()

    def test_start_is_singleton(self):
        with patch.object(c,'_thread',None),patch.object(c.threading,'Thread') as thread:
            thread.return_value.is_alive.return_value=True
            c.start();c.start()
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()

if __name__=='__main__':unittest.main()
