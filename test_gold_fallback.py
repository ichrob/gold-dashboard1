import copy
import os
import sqlite3
import unittest
from unittest.mock import patch
import gold_fallback as g
import market_review as m

T = 1794434400000  # 2026-11-11 22:00 UTC = 23:00 Zurich
NOW = T + 2*g.HOUR


def payload():
    return {'meta': {'symbol':'XAU/USD','interval':'1h','exchange_timezone':'UTC'},
            'values':[{'datetime':'2026-11-11 22:00:00','open':'4000','high':'4002','low':'3999','close':'4001'}]}


class GoldFallbackTests(unittest.TestCase):
    def test_exact_original_clock_and_missing_volume(self):
        row=g.normalize(payload(),T,NOW)
        self.assertEqual(row['openTime'],T)
        self.assertIsNone(row['volume'])
        self.assertTrue(row['researchOnly'])
        self.assertFalse(row['isExecutableQuote'])
        self.assertIsNone(g.normalize(payload(),T-g.HOUR,NOW))

    def test_reject_invalid_prices_identity_timezone_duplicate_and_open_bar(self):
        for field,value in [('open','-1'),('high','3999'),('low','4002'),('close','NaN'),('close','inf'),('close',True)]:
            d=payload();d['values'][0][field]=value
            with self.assertRaises(ValueError):g.normalize(d,T,NOW)
        for key,value in [('symbol','AAPL'),('interval','5min'),('exchange_timezone','Europe/Zurich')]:
            d=payload();d['meta'][key]=value
            with self.assertRaises(ValueError):g.normalize(d,T,NOW)
        d=payload();d['values']*=2
        with self.assertRaises(ValueError):g.normalize(d,T,NOW)
        with self.assertRaises(ValueError):g.normalize(payload(),T,T+1000)

    def test_unconfirmed_free_access_never_calls_network(self):
        with patch.dict(os.environ,{},clear=True),patch.object(g,'build_opener') as network:
            self.assertEqual(g.fetch_hour(T,now_ms=NOW)['code'],'FREE_ACCESS_UNCONFIRMED')
            network.assert_not_called()
        with patch.dict(os.environ,{'BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED':'1','TWELVEDATA_API_KEY':'demo'},clear=True):
            self.assertEqual(g.fetch_hour(T,now_ms=NOW)['code'],'KEY_NOT_CONFIGURED')

    def test_revisions_preserve_old_originals_and_duplicates_are_idempotent(self):
        db=sqlite3.connect(':memory:');a=g.normalize(payload(),T,NOW)
        with db:
            first=g.archive(db,a);g.archive(db,a)
            b=copy.deepcopy(a);b['close']=4000.5;b['fetchedAt']+=1000
            second=g.archive(db,b)
        self.assertNotEqual(first,second)
        self.assertEqual(db.execute('select count(*) from gold_fallback_observations').fetchone()[0],2)
        self.assertEqual(db.execute('select count(*) from gold_fallback_observations where volume IS NULL').fetchone()[0],2)
        self.assertEqual(a['close'],4001)
        with self.assertRaises(ValueError):g.archive(db,{**a,'source':'biquote'})
        db.close()

    def test_night_gap_does_not_invent_market_closure_or_allow_backfill(self):
        rows=[{'openTime':T-g.HOUR,'source':'biquote'},{'openTime':T+g.HOUR,'source':'biquote'}]
        evidence=m.gap_evidence(rows,g.HOUR)['gaps'][0]
        self.assertEqual(evidence['firstMissingOpenAt'],T)
        self.assertEqual(evidence['count'],1)
        self.assertEqual(evidence['sessionStatus'],'unverified')
        self.assertFalse(evidence['automaticBackfillAllowed'])


if __name__=='__main__':unittest.main()
