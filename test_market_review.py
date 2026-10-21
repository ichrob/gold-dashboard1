"""Read-only integrity monitoring never grants product or market approval."""
import copy
import datetime as dt
import unittest

import market_review as m

NOW=dt.datetime(2026,10,15,12,1,tzinfo=dt.timezone.utc)
NOW_MS=NOW.timestamp()*1000


def bars(tf, count=220, basis='XAU/USD'):
    step=m.STEPS[tf]
    latest=int(NOW_MS//step)*step-step
    return [dict(openTime=latest-(count-1-i)*step,open=4200.0,
                 close=4200.0,high=4201.0,low=4199.0,
                 instrument=basis,isOpen=False,source='test original')
            for i in range(count)]


def bundle():
    return dict(spots=dict(xaus=4200.5,spot_price_as_of=dt.datetime.fromtimestamp(
        (NOW_MS-40000)/1000,dt.timezone.utc).isoformat(),
        is_genuine_xauusd_spot=True,primary='test genuine spot',
        usd_eur=.92,usd_chf=.80,usd_eur_meta=dict(fetchedAt=NOW.isoformat(),sourceAt=None)),
        history=dict(bars_by_tf={tf:bars(tf) for tf in ('5m','15m','1h','1m','30m')}))


class MarketInputReviewTests(unittest.TestCase):
    def test_valid_frames_no_trade_approval_and_honest_fx_clock(self):
        q=m.review(bundle(),NOW.timestamp())
        self.assertTrue(q['readOnly'])
        self.assertFalse(q['affectsTradeApproval'])
        self.assertEqual(q['spot']['state'],'ok')
        for tf in ('5m','15m','1h'):
            self.assertEqual(q['frames'][tf]['state'],'ok')
            self.assertEqual(q['frames'][tf]['ema200'],'available')
        self.assertEqual(q['spotComparison']['status'],'aligned')
        self.assertEqual(q['fx']['state'],'source-time-unknown')
        self.assertFalse(q['fx']['sourceClockVerified'])
        self.assertAlmostEqual(q['fx']['eurPerChf'],1.15)

    def test_short_ema_history_is_context_only(self):
        b=bundle()
        b['history']['bars_by_tf']['1h']=bars('1h',170)
        q=m.review(b,NOW.timestamp())
        self.assertEqual(q['frames']['1h']['state'],'ok')
        self.assertEqual(q['frames']['1h']['ema200'],'context-unavailable')
        self.assertTrue(any('EMA200' in w for w in q['warnings']))
        self.assertFalse(q['affectsTradeApproval'])

    def test_wrong_instrument_stale_future_and_gap_detected(self):
        b=bundle()
        b['history']['bars_by_tf']['5m'][-1]['instrument']='GC=F'
        self.assertEqual(m.review(b,NOW.timestamp())['frames']['5m']['state'],'wrong-basis')
        b=bundle()
        b['history']['bars_by_tf']['15m'][-2]['openTime']-=m.STEPS['15m']
        self.assertEqual(m.review(b,NOW.timestamp())['frames']['15m']['state'],'invalid-ohlc')
        b=bundle()
        for x in b['history']['bars_by_tf']['5m']:
            x['openTime']-=10*m.STEPS['5m']
        self.assertEqual(m.review(b,NOW.timestamp())['frames']['5m']['state'],'stale')

    def test_recent_closed_candle_uses_close_time_and_collection_grace(self):
        step=m.STEPS['1m']
        latest_open=NOW_MS-2*step
        rows=bars('1m')
        shift=latest_open-rows[-1]['openTime']
        for row in rows:
            row['openTime']+=shift
        q=m.frame_health(rows,'1m',NOW_MS+5000)
        self.assertEqual(q['state'],'ok')
        self.assertEqual(q['lastClosedAt'],int(latest_open+step))
        self.assertEqual(q['ageSeconds'],65.0)
        self.assertEqual(m.frame_health(rows,'1m',NOW_MS+step+46000)['state'],'stale')

    def test_spot_close_comparison_requires_original_timing(self):
        b=bundle()
        b['spots']['xaus']=4250
        q=m.review(b,NOW.timestamp())
        self.assertEqual(q['spotComparison']['status'],'deviation')
        self.assertFalse(q['affectsTradeApproval'])
        b['spots']['spot_price_as_of']=(NOW-dt.timedelta(seconds=5)).isoformat()
        # Timestamp is now ~55 seconds after the 12:00 close -> still comparable.
        self.assertEqual(m.review(b,NOW.timestamp())['spotComparison']['status'],'deviation')
        b['spots']['spot_price_as_of']=(NOW-dt.timedelta(seconds=61)).isoformat()
        self.assertEqual(m.review(b,NOW.timestamp())['spotComparison']['status'],'not-comparable')
        b=bundle()
        b['spots']['spot_price_as_of']=(NOW+dt.timedelta(seconds=1)).isoformat()
        self.assertEqual(m.review(b,NOW.timestamp())['spot']['state'],'unavailable')

    def test_no_synthetic_fx_freshness_and_cross_rate_math(self):
        b=bundle()
        b['spots']['usd_eur_meta']['sourceAt']=(NOW-dt.timedelta(seconds=30)).isoformat()
        q=m.review(b,NOW.timestamp())
        self.assertEqual(q['fx']['state'],'current')
        self.assertTrue(q['fx']['sourceClockVerified'])
        b['spots']['usd_eur_meta']['sourceAt']=(NOW-dt.timedelta(seconds=100)).isoformat()
        self.assertEqual(m.review(b,NOW.timestamp())['fx']['state'],'stale')
        b['spots']['usd_chf']=0
        self.assertEqual(m.review(b,NOW.timestamp())['fx']['state'],'missing')


if __name__=='__main__':
    unittest.main()
