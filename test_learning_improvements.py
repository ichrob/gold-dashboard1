"""Prospective evidence must not learn from its own reference or future outcomes."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import product_validation_store as storage
import estimate_quality as quality
import research_learning as learning
import trade_learning_review as review
from test_research_learning import candles, report


class LearningImprovements(unittest.TestCase):
    def test_identity_isolates_model_side_and_family(self):
        model=dict(isin='TEST00000001',underlying='XAU/USD',direction='LONG',ratio=.1,strike=100,ko=100,classification=43)
        key=storage.key(model,'ask')
        self.assertTrue(storage.valid_key(key))
        for other in (storage.key(model,'bid'), storage.key(dict(model,ko=101),'ask'), storage.key(model,'ask','turbo')):
            self.assertNotEqual(key,other)
        self.assertFalse(storage.valid_key('product:anything'))

    def test_restore_isolated_product_archive_and_signed_bias(self):
        now=datetime.now(timezone.utc)
        def at(s): return (now+timedelta(seconds=s)).isoformat()
        key='product:hybrid:'+'a'*64+':ask'
        other='product:hybrid:'+'b'*64+':ask'
        pair=dict(bucket='0–60s',predictionAt=at(-30),referenceAt=at(-60),predictionReceivedAt=at(-29),truthAt=at(-30),truthReceivedAt=at(-10),prediction=10,truth=11)
        with patch.object(quality,'_errors',{}),patch.object(quality,'_seen',{}),patch.object(quality,'_pending',{}):
            quality.restore_durable([pair],now,key=key)
            quality.restore_durable([pair],now,key=key)
            q=quality.quality(key,30,now)
            self.assertEqual(q['sampleCount'],1)
            self.assertEqual(q['meanSignedError'],-1)
            self.assertEqual(quality.quality(other,30,now)['sampleCount'],0)
            with self.assertRaises(ValueError):
                quality.restore_durable([dict(pair,predictionReceivedAt=at(-1))],now,key=key)

    def test_post_purchase_observation_does_not_prove_late_entry(self):
        start=datetime.now(timezone.utc)
        rows=[(start+timedelta(minutes=18),dict(ready=False,entryTimingGate=dict(allowed=False)))]
        findings=review.findings(rows,start,start+timedelta(hours=1),'LONG',dict(unobservedStartMinutes=18))
        self.assertEqual(findings[0]['status'],'unknown')
        self.assertIn('monitoring-gap',[f['code'] for f in findings])
        self.assertTrue(all(f['causalLossProven'] is False for f in findings))

    def test_same_future_window_costs_and_protocol_change_blocks(self):
        rows=candles()
        initial=learning.enrich(report(rows),rows,day='2026-10-12')
        later=candles(930)
        result=learning.enrich(report(later),later,initial,day='2026-10-13')
        scenarios=result['learningCycle']['prospective']['costScenarios']
        for side in ('candidate','baseline'):
            self.assertEqual(scenarios['standard'][side]['trades'],scenarios['stress'][side]['trades'])
            self.assertLessEqual(scenarios['stress'][side]['index'],scenarios['standard'][side]['index'])
        initial['learningCycle']['proposal']['protocol']['horizonBars']=99
        blocked=learning.enrich(report(later),later,initial,day='2026-10-13')
        self.assertEqual(blocked['learningCycle']['status'],'blocked')
        self.assertEqual(blocked['learningCycle']['prospective']['sessions'],0)

    def test_stress_and_drawdown_must_both_pass(self):
        good=dict(candidate=dict(trades=30,index=1.2,maxDrawdownPct=1),baseline=dict(trades=30,index=1.1,maxDrawdownPct=2))
        import copy
        p=dict(costScenarios={k:copy.deepcopy(good) for k in ('standard','stress')})
        self.assertTrue(learning.robust_advantage(p))
        p['costScenarios']['stress']['candidate']['maxDrawdownPct']=3
        self.assertFalse(learning.robust_advantage(p))
        p['costScenarios']['stress']['candidate']['maxDrawdownPct']=1
        p['costScenarios']['stress']['candidate']['index']=1.05
        self.assertFalse(learning.robust_advantage(p))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class DurableProductIntegration(unittest.TestCase):
    def test_frozen_pair_restart_identity_and_no_post_truth_prediction(self):
        import psycopg
        import bob_validation_store
        import uuid
        key='product:hybrid:'+uuid.uuid4().hex*2+':ask'
        other=key[:-3]+'bid'
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        now=datetime.now(timezone.utc)
        def at(s): return (now+timedelta(seconds=s)).isoformat()
        prediction=dict(key=key,type='prediction',value=10,at=at(-30),referenceAt=at(-60))
        truth=dict(key=key,type='truth',value=11,at=at(-30))
        with psycopg.connect(dsn) as conn:
            bob_validation_store.init(conn)
            bob_validation_store.handle(conn,'write',dict(key=key,events=[prediction]))
        with psycopg.connect(dsn) as conn:
            result=bob_validation_store.handle(conn,'write',dict(key=key,events=[truth]))
            self.assertEqual(len(result['pairs']),1)
            self.assertEqual(result['pairs'][0]['prediction'],10)
            self.assertEqual(result['pairs'][0]['truth'],11)
        with psycopg.connect(dsn) as conn:
            result=storage.handle(conn,'read',dict(key=key))
            self.assertEqual(len(result['pairs']),1)
            self.assertEqual(storage.handle(conn,'read',dict(key=other))['pairs'],[])
            # Same clock cannot be overwritten by an improved recalculation.
            result=storage.handle(conn,'write',dict(key=key,events=[dict(prediction,value=11),truth]))
            self.assertEqual(result['pairs'][0]['prediction'],10)
            # A truth received BEFORE its prediction must never pair on replay.
            first=dict(truth,key=other)
            storage.handle(conn,'write',dict(key=other,events=[first]))
            storage.handle(conn,'write',dict(key=other,events=[dict(prediction,key=other)]))
            self.assertEqual(storage.handle(conn,'write',dict(key=other,events=[first]))['pairs'],[])
            for table in ('bob_product_predictions','bob_product_truths'):
                conn.execute('DELETE FROM '+table+' WHERE key=ANY(%s)',([key,other],))
