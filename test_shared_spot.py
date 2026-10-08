import unittest
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
        for name, value in [('_quote',None),('_attempted',float('-inf')),('_error',None)]:
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

    def test_failed_refresh_keeps_only_still_fresh_observation(self):
        with patch.object(product_quotes,'issuer_json',return_value=self.payload):s.current()
        with patch.object(s,'_attempted',float('-inf')),patch.object(product_quotes,'issuer_json',side_effect=OSError('offline')) as request:
            for _ in range(2):
                retained=s.current()
                self.assertEqual(retained['at'],self.payload['updatedAt'])
                self.assertTrue(retained['refreshWarning'])
            self.assertEqual(request.call_count,1)
            self.assertEqual(s._quote['at'],self.payload['updatedAt'])

    def test_reject_older_conflicting_stale_future_wrong_asset(self):
        with patch.object(product_quotes,'issuer_json',return_value=self.payload):s.current()
        for values in [dict(updatedAt=(self.now-timedelta(seconds=1)).isoformat()),dict(price=4200),dict(updatedAt=(self.now-timedelta(seconds=90)).isoformat()),dict(updatedAt=(self.now+timedelta(seconds=60)).isoformat()),dict(symbol='GCZ26')]:
            with patch.object(s,'_attempted',float('-inf')),patch.object(product_quotes,'issuer_json',return_value={**self.payload,**values}):
                with self.assertRaises(ValueError):s.current()
        with patch.object(s,'_quote',{**s._quote,'at':(self.now-timedelta(seconds=90)).isoformat()}),patch.object(s,'_error',None):
            with self.assertRaises(ValueError):s.current()

if __name__=='__main__':unittest.main()
