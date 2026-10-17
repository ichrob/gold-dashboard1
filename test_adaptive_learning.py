import copy
import os
import unittest
from datetime import datetime,timezone
from unittest.mock import Mock
import adaptive_learning as a

NOW=int(datetime(2026,10,19,5,tzinfo=timezone.utc).timestamp()*1000)

def rows(start,end,good=True,kept_gain=.4):
    out=[]
    for i,slot in enumerate(a.slots(start,end)):
        direction='LONG' if i%2 else 'SHORT';filtered=i%3==0
        value=(-.4 if good else .4) if filtered else kept_gain
        p=dict(slot=slot,at=slot+10000,valid=True,direction=direction,price=100,adx=20 if filtered else 35)
        t=dict(at=p['at']+a.HOUR,price=100+value*(1 if direction=='LONG' else -1))
        out.append((p,t))
    return out

class AdaptiveTests(unittest.TestCase):
    def selected(self):
        s=a.initial(NOW);train=rows(s['startedAt'],s['selectionEnds']-a.HOUR)
        return a.transition(s,train,s['selectionEnds']),train
    def adopted(self):
        s,train=self.selected();valid=rows(s['validationStart'],s['validationEnds'])
        return a.transition(s,train+valid,s['validationEnds']+a.HOUR+60000),train+valid
    def test_disjoint_selection_validation_and_adoption(self):
        s,train=self.selected()
        self.assertEqual(s['phase'],'validation');self.assertEqual(s['active'],'baseline')
        self.assertGreater(s['validationStart'],s['selectionEnds'])
        s,allrows=self.adopted()
        self.assertEqual(s['phase'],'monitoring');self.assertIn(s['active'],a.LABELS)
        self.assertGreater(s['lowerBound99Pct'],0)
        self.assertGreater(s['monitorStart'],s['effectiveAt'])
        self.assertEqual(s['history'][-1]['previous'],'baseline')
    def test_future_holdout_cannot_rescue_selection(self):
        s=a.initial(NOW)
        result=a.transition(s,rows(s['startedAt'],s['selectionEnds'],False)+rows(s['selectionEnds'],s['validationEnds']),s['selectionEnds'])
        self.assertEqual(result['phase'],'cooldown')
        self.assertEqual(result['active'],'baseline')
    def test_cost_stress_can_reject_gross_profitable_candidate(self):
        s=a.initial(NOW);r=rows(s['startedAt'],s['selectionEnds'],kept_gain=.08)
        m=a.metrics(r,s['startedAt'],s['selectionEnds'],'adx25')
        self.assertGreater(m['scenarios']['standard']['candidateMeanPct'],0)
        self.assertLess(m['scenarios']['stress']['candidateMeanPct'],0)
        self.assertFalse(a.advantage(m))
    def test_missing_evidence_and_single_direction_reject(self):
        s,train=self.selected();valid=rows(s['validationStart'],s['validationEnds'])
        for data in (valid[::2],[(dict(p,direction='LONG'),t) for p,t in valid]):
            result=a.transition(s,train+data,s['validationEnds']+a.HOUR+60000)
            self.assertEqual(result['active'],'baseline')
    def test_monitor_reversal_automatically_rolls_back(self):
        s,old=self.adopted();fresh=rows(s['monitorStart'],s['monitorEnd'],False)
        # Continuous liveness, but genuinely worse future outcomes.
        s['lastCheckedAt']=s['monitorEnd']
        result=a.transition(s,old+fresh,s['monitorEnd']+a.HOUR+60000)
        self.assertEqual(result['phase'],'cooldown');self.assertEqual(result['active'],'baseline')
        self.assertEqual(result['history'][-1]['event'],'automatic-rollback')
    def test_passing_monitor_uses_new_window_and_no_retraining(self):
        s,old=self.adopted();s['lastCheckedAt']=s['monitorEnd']
        result=a.transition(s,old+rows(s['monitorStart'],s['monitorEnd']),s['monitorEnd']+a.HOUR+60000)
        self.assertEqual(result['phase'],'monitoring')
        self.assertEqual(result['active'],s['active']);self.assertGreater(result['monitorStart'],s['monitorEnd'])
    def test_outage_and_missing_monitor_do_not_keep_filter(self):
        s,old=self.adopted()
        self.assertEqual(a.transition(s,old,s['lastCheckedAt']+2*a.DAY)['active'],'baseline')
        s['lastCheckedAt']=s['monitorEnd']
        self.assertEqual(a.transition(s,old,s['monitorEnd']+a.HOUR+60000)['active'],'baseline')
    def test_new_cycle_never_reuses_old_outcomes_manual_pause_persists(self):
        s=a.initial(NOW);s=a.transition(s,[],s['selectionEnds'])
        new=a.transition(s,[],s['nextCycleAt'])
        self.assertNotEqual(new['campaign'],s['campaign']);self.assertGreater(new['startedAt'],s['nextCycleAt'])
        a.revert(new,new['startedAt'],'manual',manual=True)
        self.assertEqual(a.transition(new,[],new['startedAt']+100*a.DAY)['phase'],'paused')
    def test_protocol_and_policy_allowlist(self):
        s=a.initial(NOW);s['protocol']['candidates'].append('adx10')
        self.assertEqual(a.transition(s,[],NOW),s)
        c=Mock();c.execute.return_value.fetchone.return_value=(s,)
        self.assertEqual(a.policy(c,NOW)['variant'],'unavailable')
        s,old=self.adopted();c.execute.return_value.fetchone.return_value=(s,)
        self.assertEqual(a.policy(c,s['lastCheckedAt']+a.DAY)['variant'],'baseline')
    def test_drawdown_blocks_promotion(self):
        s,train=self.selected();m=a.metrics(train,s['startedAt'],s['selectionEnds'],'adx25')
        self.assertTrue(a.advantage(m));m['scenarios']['stress']['drawdown']['candidate']=100
        self.assertFalse(a.advantage(m))

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PersistenceTests(unittest.TestCase):
    def test_tick_freezes_once_and_manual_rollback_survives_restart(self):
        import psycopg
        from psycopg import sql
        import uuid,json
        schema='adaptive_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                a.init(conn)
                conn.execute('CREATE TABLE bob_spot_observations(stream TEXT,quote_at TIMESTAMPTZ,price DOUBLE PRECISION)')
                state=a.initial(NOW);when=next(s for s in a.slots(state['startedAt'],state['selectionEnds']))+10000
                conn.execute('UPDATE bob_rule_learning SET state=%s::jsonb WHERE id=%s',(json.dumps(state),a.ID))
                market=dict(ruleVersion=a.BASE,ready=True,priceFresh=True,price=100,dataAt=when,analysisBarAt=when-300000,direction='LONG',context={'adx':26})
                calls=[]
                def analyze(*args,**kwargs):calls.append(args);return market
                a.tick(conn,{},analyze,when);a.tick(conn,{},analyze,when)
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][1]['learningPolicy']['variant'],'baseline')
                conn.commit()
                a.rollback(conn,when+10);conn.commit()
                self.assertEqual(a.get(conn)['phase'],'paused')
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_adaptive_events').fetchone()[0],1)
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
