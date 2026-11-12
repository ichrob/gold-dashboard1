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
        self.assertTrue(td.scope_allowed('XAU/USD','1h',{'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1'}))
        self.assertFalse(td.scope_allowed('CHF/EUR','1h',{'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1'}))
        self.assertTrue(td.scope_allowed('CHF/EUR','1h',{'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1',
                      'BOB_TWELVEDATA_SCOPE_CHF_EUR_1H':'1'}))

    def test_scope_rejection_does_not_call_network(self):
        with patch.dict(os.environ,{},clear=True),patch.object(td,'build_opener') as opener:
            with sqlite3.connect(':memory:') as db:
                self.assertEqual(td.fetch_research(db,'XAU/USD','5min',START,START+STEP,now_ms=NOW)['code'],'SCOPE_NOT_AUTHORIZED')
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
               'close':100+i,'researchOnly':True} for i in range(25)]
        self.assertIsNotNone(td.research_ema(rows,20))
        rows[7]['openTime']+=1000
        self.assertIsNone(td.research_ema(rows,20))


    def test_internal_indicators_and_non_executable_shadow(self):
        rows=[{'openTime':START+i*STEP,'interval':'5min','symbol':'XAU/USD',
               'open':100+i,'high':102+i,'low':99+i,
               'close':101+i,'researchOnly':True,'isExecutableQuote':False}
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

if __name__=='__main__':unittest.main()
