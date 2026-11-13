import copy
import os
import sqlite3
import unittest
from unittest.mock import patch
import twelve_research_extension as td

STEP=td.INTERVAL_MS['5min']
START=1794434400000
NOW=START+4*STEP

def example():
    return {'meta':{'symbol':'XAU/USD','interval':'5min',
                    'type':'Precious Metal','currency_base':'Gold Spot',
                    'currency_quote':'US Dollar'},
            'values':[{'datetime':'2026-11-11 22:00:00','open':'4000',
                       'high':'4002','low':'3999','close':'4001'}]}

class TwelveResearchTests(unittest.TestCase):
    def test_scopes_fail_closed(self):
        self.assertFalse(td.scope_allowed('XAU/USD','5min',{}))
        self.assertFalse(td.scope_allowed('XAU/USD','1h',{}))
        basis={'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1'}
        for interval in ('1min','5min','15min','30min','1h','1day'):
            self.assertTrue(td.scope_allowed('XAU/USD',interval,basis))
        for interval in ('4h','8h'):
            self.assertFalse(td.scope_allowed('XAU/USD',interval,{
                **basis, 'BOB_TWELVEDATA_SCOPE_XAU_USD_'+interval.upper():'1'}))
        self.assertFalse(td.scope_allowed('CHF/EUR','1h',{**basis,
            'BOB_TWELVEDATA_SCOPE_CHF_EUR_1H':'1'}))
        self.assertFalse(td.scope_allowed('EUR/CHF','1h',{**basis,
            'BOB_TWELVEDATA_SCOPE_EUR_CHF_1H':'1'}))
        self.assertFalse(td.scope_allowed('USD/CHF','1h',basis))
        self.assertTrue(td.scope_allowed('USD/CHF','1h',{**basis,
            'BOB_TWELVEDATA_SCOPE_USD_CHF_1H':'1'}))
        self.assertTrue(td.scope_allowed('EUR/USD','1h',{**basis,
            'BOB_TWELVEDATA_SCOPE_EUR_USD_1H':'1'}))

    def test_scope_rejection_does_not_call_network(self):
        with patch.dict(os.environ,{},clear=True),patch.object(td,'build_opener') as opener:
            with sqlite3.connect(':memory:') as db:
                self.assertEqual(td.fetch_research(db,'XAU/USD','5min',START,START+STEP,now_ms=NOW)['code'],'SCOPE_NOT_AUTHORIZED')
                self.assertEqual(td.fetch_earliest_timestamp(db,'EUR/CHF','1h',now_ms=NOW)['code'],'UNSUPPORTED_SCOPE')
            opener.assert_not_called()

    def test_metadata_timezone_strict(self):
        rows=td.validate_rows(example(),'XAU/USD','5min',START,START+STEP,NOW)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['researchOnly'])
        self.assertFalse(rows[0]['isExecutableQuote'])
        bad=example();bad['meta']['exchange_timezone']=None
        with self.assertRaises(ValueError):
            td.validate_rows(bad,'XAU/USD','5min',START,START+STEP,NOW)
        bad=example();bad['meta']['symbol']='EUR/CHF'
        with self.assertRaises(ValueError):
            td.validate_rows(bad,'XAU/USD','5min',START,START+STEP,NOW)

    def test_invalid_quotes_and_clocks(self):
        for field,value in [('close','nan'),('open','-2'),('low','4003'),('high','3998')]:
            bad=example();bad['values'][0][field]=value
            with self.assertRaises(ValueError):
                td.validate_rows(bad,'XAU/USD','5min',START,START+STEP,NOW)
        bad=example();bad['values'].append(copy.deepcopy(bad['values'][0]))
        with self.assertRaises(ValueError):
            td.validate_rows(bad,'XAU/USD','5min',START,START+STEP,NOW)
        with self.assertRaises(ValueError):
            td.validate_rows(example(),'XAU/USD','5min',START,START+STEP,START+1000)

    def test_revisions_and_research_provenance(self):
        rows=td.validate_rows(example(),'XAU/USD','5min',START,START+STEP,NOW)
        with sqlite3.connect(':memory:') as db:
            td.store_rows(db,rows);td.store_rows(db,rows)
            newer=copy.deepcopy(rows[0]);newer['close']=4000.5
            td.store_rows(db,[newer])
            count=db.execute('SELECT COUNT(*) FROM td_research_bars').fetchone()[0]
            self.assertEqual(count,2)
            with self.assertRaises(ValueError):
                td.store_rows(db,[{**rows[0],'researchOnly':False}])

    def test_quota_budget(self):
        with sqlite3.connect(':memory:') as db:
            with db:
                for _ in range(td.MINUTE_BUDGET):
                    self.assertTrue(td.reserve_credit(db,NOW))
                self.assertFalse(td.reserve_credit(db,NOW))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM td_credit_ledger').fetchone()[0],td.MINUTE_BUDGET)

    def test_gap_does_not_authorize_backfill(self):
        rows=[{'openTime':START,'interval':'5min'},
              {'openTime':START+3*STEP,'interval':'5min'}]
        gap=td.gaps(rows,'5min')
        self.assertEqual(len(gap),1)
        self.assertEqual(gap[0]['sessionStatus'],'unverified')
        self.assertFalse(gap[0]['automaticBackfillAllowed'])

    def test_ema_requires_contiguous_internal_bars(self):
        rows=[{'openTime':START+i*STEP,'interval':'5min','symbol':'XAU/USD',
               'close':100+i,'source':'twelvedata','researchOnly':True,
               'isExecutableQuote':False} for i in range(25)]
        self.assertIsNotNone(td.research_ema(rows,20))
        invalid=copy.deepcopy(rows)
        invalid[4]['source']='other-provider'
        self.assertIsNone(td.research_ema(invalid,20))
        rows[7]['openTime']+=1000
        self.assertIsNone(td.research_ema(rows,20))


    def test_internal_indicators_and_non_executable_shadow(self):
        rows=[{'openTime':START+i*STEP,'interval':'5min','symbol':'XAU/USD',
               'open':100+i,'high':102+i,'low':99+i,
               'close':101+i,'source':'twelvedata',
               'researchOnly':True,'isExecutableQuote':False}
              for i in range(45)]
        self.assertIsNotNone(td.research_macd(rows))
        self.assertIsNotNone(td.research_rsi(rows))
        self.assertIsNotNone(td.research_atr(rows))
        shadow=td.compare_entry_shadow(rows,direction='LONG')
        self.assertEqual(shadow['code'],'RESEARCH_SPOT_REFERENCE_ONLY')
        self.assertFalse(shadow['executableProductPnL'])
        rows[20]['openTime']+=1234
        self.assertIsNone(td.research_macd(rows))
        self.assertEqual(td.compare_entry_shadow(rows)['code'],'INSUFFICIENT_CONTIGUOUS_RESEARCH')


    def test_manual_earliest_probe_keeps_date_private(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, size):
                return b'{"datetime":"2020-01-01","unix_time":1577836800}'
        class FakeOpener:
            def __init__(self): self.called=0
            def open(self,url,timeout):
                self.called+=1
                self.url=url
                self.timeout=timeout
                return FakeResponse()
        config={'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1',
                'BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED':'1',
                'TWELVEDATA_API_KEY':'test_only_fake_key'}
        with patch.dict(os.environ,config,clear=True):
            with sqlite3.connect(':memory:',isolation_level=None) as db:
                client=FakeOpener()
                result=td.fetch_earliest_timestamp(db,'XAU/USD','1min',
                     now_ms=NOW,opener=client)
                self.assertEqual(result['code'],'OBSERVED_EARLIEST')
                self.assertEqual(client.called,1)
                self.assertIn('earliest_timestamp?',client.url)
                self.assertNotIn('2020',str(result))
                self.assertEqual(db.execute(
                    'SELECT earliest_unix FROM td_research_depth').fetchone()[0],
                    1577836800)

    def test_cross_currency_is_synthetic_internal_only(self):
        def series(symbol, close):
            return [{'source':'twelvedata','symbol':symbol,'interval':'1h',
                     'openTime':START+i*3600000,'close':close,
                     'researchOnly':True,'isExecutableQuote':False}
                    for i in range(3)]
        a=series('EUR/USD',1.10)
        b=series('USD/CHF',0.90)
        result=td.research_chf_cross(a,b)
        self.assertEqual(result['code'],'INTERNAL_FX_CROSS_RESEARCH_ONLY')
        self.assertAlmostEqual(result['EUR_CHF'],0.99)
        self.assertAlmostEqual(result['CHF_EUR'],1/0.99)
        self.assertFalse(result['isExecutableQuote'])
        b[1]['openTime']+=1000
        self.assertEqual(td.research_chf_cross(a,b)['code'],
                         'NO_MATCHING_FX_ORIGINALS')

    def test_time_series_bounded_dates_never_truncated_by_outputsize(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self,*args): return None
            def read(self,size): return b'{"meta":{"symbol":"XAU/USD","interval":"5min","type":"Precious Metal","currency_base":"Gold Spot","currency_quote":"US Dollar"},"values":[]}'
        class FakeOpener:
            def open(self,url,timeout):
                self.url=url
                return FakeResponse()
        config={'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1',
                'BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED':'1',
                'TWELVEDATA_API_KEY':'test_only_fake_key'}
        with patch.dict(os.environ,config,clear=True):
            with sqlite3.connect(':memory:',isolation_level=None) as db:
                client=FakeOpener()
                result=td.fetch_research(db,'XAU/USD','5min',
                              START,START+STEP,now_ms=NOW,opener=client)
                self.assertEqual(result['code'],'OBSERVED')
                self.assertNotIn('outputsize=',client.url)
                self.assertIn('start_date=',client.url)
                self.assertIn('end_date=',client.url)

if __name__=='__main__':unittest.main()
