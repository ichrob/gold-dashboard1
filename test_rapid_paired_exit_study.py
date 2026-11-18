"""Prospective matched-entry experiments: compare exits, not invented KO returns."""
import copy
import json
import unittest
from datetime import datetime, timezone

import rapid_leverage_study as study
import bob_diagnostics
from test_fast_gold_scalp_study import NOW, bundle


class PairedRapidExitStudyTests(unittest.TestCase):
    def test_same_original_candle_signal_and_no_hindsight(self):
        rows,err=study.candles.minute_history(bundle(),NOW,modeled=False)
        self.assertIsNone(err)
        signals=study.fast_signals(rows,NOW)
        for variant,control in study.PAIRED_EXIT_CONTROLS.items():
            self.assertIn(variant,study.SETUPS)
            self.assertIn(variant,study.FAST_SETUPS)
            self.assertEqual(signals[variant],signals[control])
            self.assertEqual(signals[variant]['direction'],'LONG')
            self.assertLessEqual(signals[variant]['closedAt'],NOW)

    def test_new_cohorts_start_at_zero_without_modifying_existing_returns(self):
        old=study.seed(NOW)
        for name in study.PAIRED_EXIT_CONTROLS:
            old['arms'].pop(name)
        old['arms']['fast1m-impulse']['levers']['10']['equityEur']=972.9
        old['arms']['fast1m-impulse']['started']=3
        frozen=copy.deepcopy(old)
        upgraded,_=study.advance(old,bundle(),NOW)
        self.assertEqual(old,frozen)
        self.assertEqual(upgraded['arms']['fast1m-impulse']['started'],3)
        self.assertEqual(upgraded['arms']['fast1m-impulse']['levers']['10']['equityEur'],972.9)
        for variant in study.PAIRED_EXIT_CONTROLS:
            arm=upgraded['arms'][variant]
            self.assertEqual(arm['started'],1)
            self.assertEqual(arm['closed'],0)
            self.assertEqual(arm['levers']['10']['equityEur'],1000.)

    def test_all_three_pairs_share_entry_initial_stop_and_costs(self):
        state,_=study.advance(study.seed(NOW),bundle(),NOW)
        for variant,control in study.PAIRED_EXIT_CONTROLS.items():
            a=state['arms'][variant]['position']
            b=state['arms'][control]['position']
            self.assertIsNotNone(a)
            self.assertEqual(a['entrySourceAt'],b['entrySourceAt'])
            self.assertEqual(a['entry'],b['entry'])
            self.assertEqual(a['stop'],b['stop'])
            self.assertEqual(a['risk'],b['risk'])
            self.assertEqual(a['costAssumptions'],b['costAssumptions'])
            self.assertEqual(a['pairedSignalKey'],b['pairedSignalKey'])
            self.assertEqual(a['pairedControl'],control)
            self.assertLess(a['target'],b['target'])
            self.assertFalse(a['realOrders'])
            self.assertFalse(a['productReturnVerified'])

    def test_earlier_target_exit_does_not_close_control(self):
        state,_=study.advance(study.seed(NOW),bundle(),NOW)
        p=state['arms']['fast1m-impulse-exit10']['position']
        price=p['entry']+1.1*p['risk']
        following,finished=study.advance(state,bundle(NOW+30000,spot=price),NOW+30000)
        closed=next(x for x in finished if x['setup']=='fast1m-impulse-exit10')
        self.assertEqual(closed['exitReason'],'target-observed')
        self.assertAlmostEqual(closed['exitPrice'],price)
        self.assertIsNotNone(following['arms']['fast1m-impulse']['position'])
        self.assertEqual(following['arms']['fast1m-impulse-exit10']['closed'],1)
        self.assertEqual(following['arms']['fast1m-impulse-exit10']['exitReasonCounts']['target-observed'],1)
        self.assertEqual(following['arms']['fast1m-impulse-exit10']['completedObservedRCount'],1)
        self.assertAlmostEqual(following['arms']['fast1m-impulse-exit10']['completedObservedR'],1.1)
        self.assertEqual(following['arms']['fast1m-impulse-exit10']['levers']['10']['completed'],1)
        self.assertFalse(closed['results']['10']['productReturnVerified'])

    def test_variant_moves_stop_to_break_even_before_control(self):
        state,_=study.advance(study.seed(NOW),bundle(),NOW)
        p=state['arms']['fast1m-impulse-exit10']['position']
        favorable=p['entry']+.55*p['risk']
        after,_=study.advance(state,bundle(NOW+30000,spot=favorable),NOW+30000)
        strict=after['arms']['fast1m-impulse-exit10']['position']
        baseline=after['arms']['fast1m-impulse']['position']
        self.assertIsNotNone(strict)
        self.assertGreaterEqual(strict['stop'],strict['entry'])
        self.assertLess(baseline['stop'],baseline['entry'])
        # Reversal can stop new variant on the next real observation, but
        # the old control stays open and never inherits the new rule.
        reverse=p['entry']-.2*p['risk']
        later,done=study.advance(after,bundle(NOW+60000,spot=reverse),NOW+60000)
        match=next(x for x in done if x['setup']=='fast1m-impulse-exit10')
        self.assertEqual(match['exitReason'],'stop-observed')
        self.assertEqual(match['exitPrice'],reverse)
        self.assertIsNotNone(later['arms']['fast1m-impulse']['position'])

    def test_source_gap_does_not_book_profits(self):
        state,_=study.advance(study.seed(NOW),bundle(),NOW)
        later,completed=study.advance(state,bundle(NOW+120000,spot=4070.),NOW+120000)
        pair=[p for p in completed if p['setup'] in study.PAIRED_EXIT_CONTROLS]
        self.assertEqual(len(pair),3)
        self.assertTrue(all(p['status']=='inconclusive' and p['results'] is None for p in pair))
        for name in study.PAIRED_EXIT_CONTROLS:
            self.assertEqual(later['arms'][name]['levers']['10']['equityEur'],1000.)
            self.assertEqual(later['arms'][name]['completedObservedRCount'] if
                             'completedObservedRCount' in later['arms'][name] else 0,0)

    def test_no_original_minute_data_blocks_all_six_fast_strategies(self):
        b=bundle()
        b['history']['bars_by_tf']['1m'].pop(15)
        st,_=study.advance(study.seed(NOW),b,NOW)
        for name in study.FAST_SETUPS:
            self.assertEqual(st['arms'][name]['started'],0)
            self.assertEqual(st['arms'][name]['lastReason'],'original-1m-coverage-missing')

    def test_ten_studies_visible_but_never_raw_cases(self):
        state,_=study.advance(study.seed(NOW),bundle(),NOW)
        class Conn:
            def execute(self,*args):
                return self
            def fetchone(self):
                return (state,)
        raw=study.report(Conn())
        self.assertEqual(len(raw['setups']),10)
        private=raw['setups'][7]
        private['hiddenToken']='do-not-forward'
        brief=bob_diagnostics.rapid_leverage_brief(raw)
        self.assertEqual(len(brief['setups']),10)
        self.assertEqual(brief['configurationsReported'],70)
        self.assertEqual(brief['setups'][7]['pairedControl'],'fast1m-impulse')
        self.assertNotIn('hiddenToken',json.dumps(brief))
        self.assertNotIn('pairedSignalKey',json.dumps(brief))
        self.assertFalse(brief['productReturnVerified'])
        self.assertFalse(brief['strategyWinnerConfirmed'])

if __name__=="__main__":
    unittest.main()
