import copy
import json
import unittest
from unittest.mock import Mock
import research_restart as r
import simulation_estimates as e
from test_research_restart import NOW, sample


class EstimateTests(unittest.TestCase):
    def test_missing_candle_is_marked_and_does_not_mutate_originals(self):
        b,m=sample()
        target=m['analysisBarAt']
        b['history']['bars_by_tf']['15m']=[dict(openTime=target-900000,
            instrument='XAU/USD',isOpen=False,close=3998.)]
        before=copy.deepcopy((b,m))
        strict,_=r.advance(r.seed(NOW),b,m,NOW)
        model,_=r.advance(r.seed(NOW),b,m,NOW,modeled=True)
        self.assertEqual(strict['studies']['entry-delay']['started'],0)
        self.assertEqual(model['studies']['entry-delay']['started'],1)
        quality=model['lastInput']
        self.assertTrue(quality['simulationUsable'])
        self.assertFalse(quality['verified'])
        self.assertTrue(quality['estimated'])
        candle=quality['estimatedCandle']
        self.assertEqual(candle['close'],3998.)
        self.assertFalse(candle['observedRangeKnown'])
        self.assertEqual(candle['anchorAt'],target)
        self.assertEqual((b,m),before)

    def test_open_future_large_gap_and_unanchored_candles_are_not_filled(self):
        b,m=sample();target=m['analysisBarAt']
        base=dict(openTime=target-900000,instrument='XAU/USD',isOpen=False,close=3998.)
        for bars in ([],[{**base,'estimated':True}], [{**base,'openTime':target-2700000}],
                     [base,dict(openTime=target,providerIsOpen=True)],
                     [{**base,'instrument':'GC'}]):
            b['history']['bars_by_tf']['15m']=bars
            self.assertIsNone(e.candle(b,'15m',target,NOW))
        b['history']['bars_by_tf']['15m']=[base]
        self.assertIsNone(e.candle(b,'15m',NOW,NOW))

    def test_short_gap_finishes_only_model_and_remains_excluded_from_originals(self):
        strict=r.seed(NOW);model=r.seed(NOW);original_closed=[];model_closed=[]
        for elapsed in range(0,3600001,30000):
            # Skip four source cycles: 150s between observed originals.
            if 900000 <= elapsed <= 990000:
                continue
            b,m=sample(NOW+elapsed,4000+elapsed/90000)
            strict,closed=r.advance(strict,b,m,NOW+elapsed);original_closed+=closed
            model,closed=r.advance(model,b,m,NOW+elapsed,modeled=True);model_closed+=closed
        self.assertTrue(all(c['status']=='inconclusive' for c in original_closed))
        self.assertEqual(len(model_closed),3)
        self.assertTrue(all(c['status']=='complete' and c['estimatedUsed'] for c in model_closed))
        self.assertEqual(model['studies']['entry-delay']['estimatedComplete'],1)
        self.assertTrue(all(c['id'].endswith(':model-v1') for c in model_closed))
        self.assertTrue(all(not c['originalResultVerified'] for c in model_closed))

    def test_missing_exit_uses_frozen_original_anchor_with_age_limit(self):
        model=r.seed(NOW);out=[]
        for elapsed in range(0,3600000,30000):
            b,m=sample(NOW+elapsed,4000+elapsed/90000)
            model,_=r.advance(model,b,m,NOW+elapsed,modeled=True)
        b,m=sample(NOW+3510000,4039.)
        model,out=r.advance(model,b,m,NOW+3600000,modeled=True)
        self.assertEqual(len(out),3)
        self.assertTrue(all(c['status']=='complete' and c['estimatedUsed'] for c in out))
        self.assertEqual(out[0]['exit']['originalSourceAt'],NOW+3570000)
        self.assertEqual(out[0]['exit']['dataMode'],'estimated-price')
        # Estimates cannot become anchors and prolong an outage indefinitely.
        q=model['lastInput'];previous=model['lastOriginalInput']
        self.assertTrue(previous['verified'])
        later=e.input_quality({**q,'verified':False},b,m,NOW+3900000,'15m',previous)
        self.assertFalse(later['simulationUsable'])

    def test_long_gap_and_future_or_conflicting_input_remain_blocked(self):
        b,m=sample();model,_=r.advance(r.seed(NOW),b,m,NOW,modeled=True)
        b,m=sample(NOW+3600000,4100.)
        model,out=r.advance(model,b,m,NOW+3600000,modeled=True)
        self.assertTrue(all(c['status']=='inconclusive' for c in out))
        b,m=sample(NOW+120000)
        previous=dict(verified=True,sourceAt=NOW,price=4000.,analysisBarAt=NOW-900000)
        for changes in ({'price':4005.},{'dataAt':NOW+240000}):
            q=e.input_quality({'verified':False},b,{**m,**changes},NOW+120000,'15m',previous)
            self.assertFalse(q['simulationUsable'])

    def test_tick_persists_both_runs_without_restarting_original_campaign(self):
        b,m=sample();state=r.seed(NOW-60000)
        conn=Mock();conn.execute.return_value.fetchone.return_value=(state,)
        r.tick(conn,b,m,NOW)
        args=next(c.args[1] for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE bob_quality_campaign'))
        saved=json.loads(args[0]);model=saved['modeledSimulation']
        self.assertEqual(saved['startedAt'],NOW-60000)
        self.assertEqual(model['startedAt'],NOW)
        self.assertEqual(model['deadlineAt'],saved['deadlineAt'])
        conn.reset_mock();conn.execute.return_value.fetchone.return_value=(saved,)
        b,m=sample(NOW+30000)
        r.tick(conn,b,m,NOW+30000)
        args=next(c.args[1] for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE bob_quality_campaign'))
        self.assertEqual(json.loads(args[0])['modeledSimulation']['startedAt'],NOW)


if __name__=='__main__':unittest.main()
