import copy
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import xaus_spot as x

NOW = 1793289000
STAMP = datetime.fromtimestamp(NOW-5, timezone.utc).isoformat()

def payload():
    return dict(xau=dict(price=4000.,currency='USD',unit='oz'),spot_usd_oz=4000.,
                data_state=dict(status='fresh',source='upstream',as_of=STAMP),updated_at=STAMP)

class XausSpotTests(unittest.TestCase):
    def test_original_clock_and_identity(self):
        q=x.parse(payload(),NOW)
        self.assertEqual(q['at'],STAMP)
        self.assertTrue(q['observed'])
        for field,value in [('currency','EUR'),('unit','gram'),('price',True),('price',float('nan'))]:
            d=payload();d['xau'][field]=value
            with self.assertRaises(ValueError):x.parse(d,NOW)
        for field,value in [('status','stale'),('source','cache'),('as_of','2020-01-01T00:00:00Z'),('as_of','2030-01-01T00:00:00Z'),('as_of','2026-10-29T15:00:00')]:
            d=payload();d['data_state'][field]=value
            with self.assertRaises(ValueError):x.parse(d,NOW)

    def test_cache_and_rate_limit(self):
        import product_quotes
        from urllib.error import HTTPError
        with patch.object(x,'_quote',None),patch.object(x,'_attempted',float('-inf')),patch.object(x,'_retry_at',0),patch.object(x.time,'time',return_value=NOW),patch.object(x.time,'monotonic',return_value=100):
            with patch.object(product_quotes,'issuer_json',return_value=payload()) as request:
                a=x.current();a['price']=1
                self.assertEqual(x.current()['price'],4000)
                request.assert_called_once()
            with patch.object(x.time,'monotonic',return_value=131),patch.object(product_quotes,'issuer_json',side_effect=HTTPError(x.URL,429,'rate',{'Retry-After':'600'},None)) as request:
                self.assertIsNone(x.current())
                self.assertIsNone(x.current())
                request.assert_called_once()
                self.assertEqual(x._retry_at,731)

if __name__=='__main__':unittest.main()
