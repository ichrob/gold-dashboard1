import copy
import json
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from urllib.error import HTTPError
import cme_reference as c
import auto_collection as a
import future_estimate as f

NOW = datetime(2026, 10, 6, 17, tzinfo=timezone.utc)

def fixture():
    return {'quoteDelayed':True, 'quotes':[{'quoteCode':'GCZ6', 'productId':437,
        'productCode':'GC','productName':'Gold Futures','exchangeCode':'XCEC',
        'expirationMonth':'DEC 2026','expirationCode':'Z6','mdKey':'GCZ6-XCEC-G',
        'lastTradeDate':'2026-12-29T06:00:00Z','last':'4187.5',
        'updated':(NOW-timedelta(minutes=10)).isoformat(), 'lastUpdated':NOW.isoformat()}]}

class CmeReferenceTests(unittest.TestCase):
    def test_original_trade_time_not_response_time(self):
        p=fixture();r=c.parse(p,NOW)
        self.assertEqual(r['underlyingAt'],p['quotes'][0]['updated'])
        self.assertEqual(r['contract'],'GCZ26')
        self.assertEqual(r['underlyingPriceUsd'],4187.5)
        self.assertFalse(r['eligible']);self.assertFalse(r['isExchangeRealtime'])

    def test_wrong_contract_invalid_price_and_old_trade_are_rejected(self):
        cases=[('expirationMonth','DEC 2025'),('exchangeCode','OTHER'),('productId',438),
               ('quoteCode','GCG7'),('last',True),('last','nan'),('last','-'),
               ('updated',(NOW-timedelta(seconds=1801)).isoformat()),
               ('updated',(NOW+timedelta(seconds=1)).isoformat()),('updated','2026-10-06T16:50:00')]
        for key,value in cases:
            p=fixture();p['quotes'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):c.parse(p,NOW)
        p=fixture();p['quotes'].append(copy.deepcopy(p['quotes'][0]))
        with self.assertRaises(ValueError):c.parse(p,NOW)

    def test_backoff_honors_retry_after_without_repeated_network_calls(self):
        error=HTTPError(c.URL,429,'private',{'Retry-After':'1200'},None)
        with patch.object(c,'_cache',None),patch.object(c,'_next_fetch',0),patch.object(c,'_failures',0),patch.object(c,'_error',None),patch.object(c.time,'monotonic',return_value=100),patch.object(c,'urlopen',side_effect=error) as fetch:
            with self.assertRaises(HTTPError):c.fetch_reference()
            with self.assertRaises(OSError):c.fetch_reference()
            fetch.assert_called_once()
            self.assertEqual(c.failure()[0],1200)
            self.assertNotIn('private',c.failure()[1])

    def test_yahoo_failure_recovers_estimate_from_cme_and_archived_spot(self):
        ref=c.parse(fixture(),NOW)
        observations=[dict(at=(NOW-timedelta(seconds=s)).isoformat(),price=4160+s*.001,
                           symbol='XAU',currency='USD') for s in range(660,-1,-20)]
        error=HTTPError('https://example.invalid',429,'limited',{},None)
        with patch.object(a,'_research',{}),patch.object(a,'_next_source',0),patch.object(a,'_source_error',None),patch.object(a,'_failures',0),patch.object(a,'enabled',return_value=True),patch.object(f,'_research_reference',{}),patch.object(f,'_spot_ticks',[]),patch.object(f,'_ticks',[]),patch.object(f,'ensure_collector'),patch.object(a.future_analysis,'fetch_reference',side_effect=error),patch.object(a.cme_reference,'fetch_reference',return_value=ref) as backup,patch.object(a.bob_validation_store,'request',return_value={'pairs':[]}),patch.object(a.bob_market_store,'request',return_value={'observations':observations}),patch.object(a.estimate_quality,'restore_durable'),patch.object(a.estimate_quality,'record'),patch.object(a.estimate_quality,'observe'),patch.object(a,'datetime') as clock:
            clock.now.return_value=NOW
            a.tick(NOW)
            r=a.status()
            backup.assert_called_once()
            self.assertTrue(r['estimateAvailable'])
            self.assertEqual(r['referenceSource'],ref['source'])
            self.assertEqual(r['referenceAt'],ref['underlyingAt'])
            self.assertFalse(r['ready'])
            self.assertIsNone(r['sourceStatus'])

if __name__=='__main__':unittest.main()
