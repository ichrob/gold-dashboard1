"""Prospective relaxed arm: fresh prices, frozen targets, unchanged controls."""
import unittest
from unittest.mock import patch
import intraday_timing_study as s
from test_intraday_fresh_continuation import opportunity
from test_intraday_timing_study import NOW

class RelaxedFollow(unittest.TestCase):
    def test_window_both_directions_and_next_close_expiry(self):
        for side in ('LONG','SHORT'):
            b,m=opportunity(side)
            rows,_=s.minute_history(b,NOW)
            for age in (90001,180000,299999):
                self.assertIsNone(s.fresh_continuation_signal(rows,NOW+age)['direction'])
                sig=s.fresh_continuation_signal(rows,NOW+age,relaxed=True)
                self.assertEqual(sig['direction'],side)
                self.assertEqual(sig['closedAt'],NOW)
            self.assertIsNone(s.fresh_continuation_signal(rows,NOW+300000,relaxed=True)['direction'])

    def test_extension_warning_not_blanket_block(self):
        b,m=opportunity()
        for row in b['history']['bars_by_tf']['1m'][-5:]:
            row.update(open=4017.,high=4020.,low=4016.,close=4019.)
        rows,_=s.minute_history(b,NOW)
        self.assertIsNone(s.fresh_continuation_signal(rows,NOW)['direction'])
        sig=s.fresh_continuation_signal(rows,NOW,relaxed=True)
        self.assertEqual(sig['direction'],'LONG')
        self.assertIn('ema-extension-over-2atr',sig['riskWarnings'])

    def test_actual_worker_entry_after_old_window_and_duplicate_guard(self):
        for side in ('LONG','SHORT'):
            b,m=opportunity(side)
            rows,_=s.minute_history(b,NOW)
            at=NOW+180000
            # Supply fully validated source history separately to isolate the window.
            with patch.object(s,'minute_history',return_value=(rows,None)), patch.object(s,'source',return_value=dict(available=True,estimated=False,at=at,price=b['spots']['xaus'])):
                state,_=s.advance(s.seed(at),b,m,{}, {},at)
                self.assertEqual(state['arms']['original:follow5:30']['started'],0)
                arm=state['arms']['original:relaxedfollow5:30']
                self.assertEqual(arm['started'],1)
                self.assertEqual(arm['position']['signalClosedAt'],NOW)
                self.assertGreater(arm['position']['risk'],0)
                state,_=s.advance(state,b,m,{}, {},at+1000)
                self.assertEqual(state['arms']['original:relaxedfollow5:30']['started'],1)

    def test_price_drift_staleness_and_missing_originals(self):
        b,m=opportunity()
        b['spots']['xaus']+=20
        state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertEqual(state['arms']['original:relaxedfollow5:30']['started'],0)
        self.assertEqual(state['arms']['original:relaxedfollow5:30']['reason'],'entry-price-drift-over-0.8atr')
        b,m=opportunity()
        del b['history']['bars_by_tf']['1m'][110]
        state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertEqual(state['arms']['original:relaxedfollow5:30']['started'],0)
        b,m=opportunity()
        b['spots']['spot_price_as_of']='2026-11-06T09:00:00+00:00'
        state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertEqual(state['arms']['original:relaxedfollow5:30']['started'],0)
