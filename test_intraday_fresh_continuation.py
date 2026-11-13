"""Causal 5m continuation hypothesis: shorter LONG/SHORT participation, shadow only."""
import copy
import unittest
from unittest.mock import patch

import intraday_timing_study as s
from test_intraday_timing_study import NOW, sample


def opportunity(side='LONG'):
    """One fresh two-bar continuation but NO new 15-minute high/low breakout."""
    b, m = sample(NOW, price=4002.6, trend='LONG')
    raw = b['history']['bars_by_tf']['1m']
    # A dated older wick means the old 15-minute breakout is NOT refreshed.
    raw[102].update(open=4000., high=4005., low=3999., close=4000.)
    for i in range(105, 110):
        raw[i].update(open=4000.2, high=4001.15, low=4000.1, close=4001.0)
    for i in range(110, 115):
        raw[i].update(open=4000.9, high=4001.8, low=4000.7, close=4001.5)
    for i in range(115, 120):
        raw[i].update(open=4001.5, high=4002.8, low=4001.3, close=4002.6)
    if side == 'SHORT':
        for row in raw:
            row.update(open=8000-row['open'], close=8000-row['close'],
                       high=8000-row['low'], low=8000-row['high'])
        b['spots']['xaus'] = 3997.4
        m['trendContext']['direction'] = 'SHORT'
    m.update(ready=True, priceFresh=True, direction='NEUTRAL')
    return b, m


class FreshContinuation(unittest.TestCase):
    def test_new_closed_bar_reopens_both_sides_without_reusing_15m_clock(self):
        for side in ('LONG', 'SHORT'):
            with self.subTest(side=side):
                b, m = opportunity(side)
                rows, reason = s.minute_history(b, NOW)
                self.assertIsNone(reason)
                self.assertIsNone(s.frame_signal(rows,5,NOW)['direction'])
                sig = s.fresh_continuation_signal(rows, NOW)
                self.assertEqual(sig['direction'],side)
                self.assertEqual(sig['setup'],'closed-5m-follow-through')
                self.assertEqual(sig['closedAt'],NOW)
                self.assertLessEqual(sig['extensionAtr'],2.0)
                self.assertTrue(s.gate(sig,m['trendContext'],s.VARIANTS['follow5'])[0])
                before = copy.deepcopy((b,m))
                state, done = s.advance(s.seed(NOW),b,m,{}, {},NOW)
                self.assertEqual((b,m),before)
                self.assertFalse(done)
                self.assertEqual(state['arms']['original:base5:30']['started'],0)
                a=state['arms']['original:follow5:30']
                self.assertEqual(a['started'],1)
                self.assertEqual(a['followThroughEntries'],1)
                self.assertEqual(a['baselineOverlapEntries'],0)
                self.assertEqual(a['position']['direction'],side)
                self.assertFalse(a['position']['realOrders'])
                self.assertFalse(a['position']['productReturnVerified'])
                self.assertEqual(a['position']['horizonMinutes'],30)
                self.assertIn('original:follow5:300',state['arms'])

    def test_freshness_future_bar_and_late_reuse_are_rejected(self):
        b, m = opportunity()
        rows,_ = s.minute_history(b,NOW)
        original=s.fresh_continuation_signal(rows,NOW)
        b['history']['bars_by_tf']['1m'].append({
            'openTime':NOW,'open':5000.,'high':5001.,'low':4999.,'close':5000.,
            'instrument':'XAU/USD','source':'test','isOpen':False})
        fresh,_=s.minute_history(b,NOW)
        self.assertEqual(s.fresh_continuation_signal(fresh,NOW),original)
        late=s.fresh_continuation_signal(rows,NOW+2*s.MINUTE)
        self.assertIsNone(late['direction'])
        self.assertEqual(late['reason'],'continuation-signal-not-fresh')

    def test_reject_overshoot_and_hour_opposition(self):
        b,m=opportunity()
        # A 5-minute jump too far away from EMA20 is not a safe fresh entry.
        for row in b['history']['bars_by_tf']['1m'][-5:]:
            row.update(open=4017.,high=4020.,low=4016.,close=4019.)
        rows,_=s.minute_history(b,NOW)
        sig=s.fresh_continuation_signal(rows,NOW)
        self.assertIsNone(sig['direction'])
        self.assertEqual(sig['reason'],'continuation-overextended-2atr')
        b,m=opportunity()
        rows,_=s.minute_history(b,NOW)
        signal=s.fresh_continuation_signal(rows,NOW)
        self.assertFalse(s.gate(signal,dict(available=True,direction='SHORT'),s.VARIANTS['follow5'])[0])

    def test_no_entry_with_missing_original_candles_or_stale_spot(self):
        b,m=opportunity()
        del b['history']['bars_by_tf']['1m'][110]
        state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertEqual(state['arms']['original:follow5:30']['started'],0)
        b,m=opportunity()
        b['spots']['spot_price_as_of']='2026-11-06T09:00:00+00:00'
        state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertEqual(state['arms']['original:follow5:30']['started'],0)

    def test_existing_arms_survive_new_variant_without_reset(self):
        b,m=opportunity()
        old=s.seed(NOW-30000)
        old['arms']['original:base5:30']=dict(
            mode='original',variant='base5',horizonMinutes=30,label='existing',
            started=12,closed=7,inconclusive=0,estimatedClosed=0,originalClosed=7,
            originalSumNetPct=-.7,estimatedSumNetPct=0.,sumNetPct=-.7,worstNetPct=-.3,
            maxAdversePct=1.2,falseStarts=3,lastSignal=None,position=None,blockCounts={},
            reversalExits=0,reversalEntries=0)
        next_state,_=s.advance(old,b,m,{}, {},NOW)
        self.assertEqual(old['arms']['original:base5:30']['started'],12)
        self.assertEqual(next_state['arms']['original:base5:30']['started'],12)
        self.assertEqual(next_state['arms']['original:base5:30']['originalSumNetPct'],-.7)
        self.assertEqual(next_state['arms']['original:follow5:30']['started'],1)


if __name__ == '__main__':
    unittest.main()
