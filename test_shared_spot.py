import unittest
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import spot_data as s
import product_quotes
import future_estimate
import market_cards
import server

class SharedSpotTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('_retry_at',0),('_route',0),('_quote',None),('_attempted',float('-inf')),('_error',None),('_near_expiry_retried_at',None)]:
            p=patch.object(s,name,value);p.start();self.addCleanup(p.stop)
        self.now=datetime.now(timezone.utc)
        self.payload=dict(symbol='XAU',name='Gold',currency='USD',exchangeRate=1,price=4141.8,updatedAt=self.now.isoformat())

    def test_consumers_share_one_observation_and_request(self):
        with patch.object(product_quotes,'issuer_json',return_value=self.payload) as request:
            with ThreadPoolExecutor(max_workers=8) as pool:
                quotes=list(pool.map(lambda _:s.current(),range(8)))
            card=market_cards.fetch_spot();model=future_estimate.fetch_spot_tick()
            with patch.object(server,'_live_cache',None),patch.object(server,'fetch_json',side_effect=OSError('history unavailable')):
                bundle=server.build_live_bundle()
            self.assertEqual(request.call_count,1)
            for q in quotes+[card,model]:
                self.assertEqual(q['price'],bundle['spots']['xaus'])
                self.assertEqual(q['at'],bundle['spots']['spot_price_as_of'])
            quotes[0]['price']=9999
            self.assertEqual(s.current()['price'],4141.8)
            self.assertTrue(bundle['spots']['is_genuine_xauusd_spot'])

    def test_bundle_rechecks_near_expiry_with_original_provider_timestamp(self):
        old=(self.now-timedelta(seconds=35)).isoformat()
        newer=(self.now-timedelta(seconds=2)).isoformat()
        source='Gold-API.com · XAU/USD Spot'
        original=(4100.,35.,None,source,True,old)
        refreshed={'price':4141.8,'at':newer,'source':source}
        with patch.object(s,'current',return_value=refreshed) as current:
            row=server.recheck_spot_before_bundle(original,now=self.now.timestamp())
        self.assertEqual(current.call_count,1)
        self.assertEqual(row[0],4141.8)
        self.assertEqual(row[5],newer)
        self.assertAlmostEqual(row[1],2,delta=.1)
        self.assertTrue(row[4])

    def test_late_bundle_recheck_never_promotes_stale_or_conflicting_quote(self):
        old=(self.now-timedelta(seconds=61)).isoformat()
        source='Gold-API.com · XAU/USD Spot'
        original=(4100.,1.,None,source,True,old)
        with patch.object(s,'current',side_effect=ValueError("stale")) as current:
            row=server.recheck_spot_before_bundle(original,now=self.now.timestamp())
        current.assert_called_once()
        self.assertEqual(row[5],old)
        self.assertGreater(row[1],60)
        self.assertEqual(row[0],4100.)
        with patch.object(s,'current',return_value={'price':9999.,
            'at':self.now.isoformat(),'source':'Unverified'}) as current:
            row=server.recheck_spot_before_bundle(original,now=self.now.timestamp())
        self.assertEqual(row[0],4100.)
        self.assertEqual(row[5],old)
        with patch.object(s,'current') as current:
            fresh=server.recheck_spot_before_bundle(
                (4141.8,10.,None,source,True,(self.now-timedelta(seconds=10)).isoformat()),
                now=self.now.timestamp())
        current.assert_not_called()
        self.assertAlmostEqual(fresh[1],10,delta=.1)

    def test_failed_refresh_keeps_only_still_fresh_observation(self):
        with patch.object(product_quotes,'issuer_json',return_value=self.payload):s.current()
        with patch.object(s,'_attempted',float('-inf')),patch.object(product_quotes,'issuer_json',side_effect=OSError('offline')) as request:
            for _ in range(2):
                retained=s.current()
                self.assertEqual(retained['at'],self.payload['updatedAt'])
                self.assertTrue(retained['refreshWarning'])
            self.assertEqual(request.call_count,1)
            self.assertEqual(s._quote['at'],self.payload['updatedAt'])

    def test_near_expiry_observation_gets_one_bounded_early_retry(self):
        payload={**self.payload,'updatedAt':(self.now-timedelta(seconds=35)).isoformat()}
        with patch.object(product_quotes,'issuer_json',return_value=payload) as request:
            self.assertEqual(s.current()['at'],payload['updatedAt'])
            self.assertEqual(request.call_count,1)
            with patch.object(s,'_attempted',time.monotonic()-s.NEAR_EXPIRY_RETRY_SECONDS-1):
                self.assertEqual(s.current()['at'],payload['updatedAt'])
            self.assertEqual(request.call_count,2)
            # Repeating the same original source time cannot create a fast loop.
            with patch.object(s,'_attempted',time.monotonic()-s.NEAR_EXPIRY_RETRY_SECONDS-1):
                self.assertEqual(s.current()['at'],payload['updatedAt'])
            self.assertEqual(request.call_count,2)

    def test_ageing_cached_quote_refreshes_before_minute_signal_expires(self):
        # Provider observation is already 35s old, but our HTTP cache is only 6s old.
        # Stacked cache lifetimes used to retain it until the 50s threshold.
        old=(self.now-timedelta(seconds=35)).isoformat()
        s._quote={'price':4100.,'at':old,'source':'Gold-API.com · XAU/USD Spot'}
        s._attempted=time.monotonic()-6
        with patch.object(product_quotes,'issuer_json',return_value=self.payload) as request:
            refreshed=s.current()
        request.assert_called_once()
        self.assertEqual(refreshed['at'],self.payload['updatedAt'])
        self.assertEqual(refreshed['price'],self.payload['price'])

    def test_early_retry_can_replace_quote_just_after_it_expires(self):
        expired_at=(self.now-timedelta(seconds=61)).isoformat()
        s._quote={'price':4100.,'at':expired_at,'source':'Gold-API.com · XAU/USD Spot'}
        s._attempted=time.monotonic()-s.NEAR_EXPIRY_RETRY_SECONDS-1
        with patch.object(product_quotes,'issuer_json',return_value=self.payload) as request:
            self.assertEqual(s.current()['at'],self.payload['updatedAt'])
        self.assertEqual(request.call_count,1)
        self.assertIsNone(s._near_expiry_retried_at)

    def test_reject_older_conflicting_stale_future_wrong_asset(self):
        with patch.object(product_quotes,'issuer_json',return_value=self.payload):s.current()
        for values in [dict(updatedAt=(self.now-timedelta(seconds=1)).isoformat()),dict(price=4200),dict(updatedAt=(self.now-timedelta(seconds=90)).isoformat()),dict(updatedAt=(self.now+timedelta(seconds=60)).isoformat()),dict(symbol='GCZ26')]:
            with patch.object(s,'_attempted',float('-inf')),patch.object(product_quotes,'issuer_json',return_value={**self.payload,**values}):
                with self.assertRaises(ValueError):s.current()
        with patch.object(s,'_quote',{**s._quote,'at':(self.now-timedelta(seconds=90)).isoformat()}),patch.object(s,'_error',None):
            with self.assertRaises(ValueError):s.current()

    def test_failed_clock_rotates_route_then_recovers_without_redating(self):
        stale={**self.payload, 'updatedAt':(self.now-timedelta(seconds=90)).isoformat()}
        with patch.object(product_quotes,'issuer_json',side_effect=[stale,self.payload]) as request:
            with self.assertRaises(ValueError):s.current()
            self.assertIsNone(s._quote)
            with self.assertRaises(ValueError):s.current()
            self.assertEqual(request.call_count,1)
            with patch.object(s,'_attempted',float('-inf')): restored=s.current()
            self.assertEqual(request.call_args.args[0],s.URL+'/USD')
            self.assertEqual(restored['at'],self.payload['updatedAt'])
            self.assertIsNone(restored['refreshWarning'])

    def test_rate_limit_does_not_rotate_or_bypass_wait(self):
        from urllib.error import HTTPError
        with patch.object(product_quotes,'issuer_json',side_effect=HTTPError(s.URL,429,'limit',{'Retry-After':'600'},None)) as request:
            with self.assertRaises(ValueError):s.current()
            with patch.object(s,'_attempted',float('-inf')):
                with self.assertRaises(ValueError):s.current()
            self.assertEqual(request.call_count,1)
            self.assertEqual(s._route,0)

if __name__=='__main__':unittest.main()
