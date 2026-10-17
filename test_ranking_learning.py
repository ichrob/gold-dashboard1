import copy
import json
import os
import unittest
from datetime import datetime,timezone
from unittest.mock import Mock,patch
import ranking_learning as r

NOW=int(datetime(2026,10,19,5,tzinfo=timezone.utc).timestamp()*1000)

def candidates(at):
    return [dict(isin=i,score=score,direction='LONG',paperOnly=False,
        quote=dict(isin=i,currency='EUR',source='test',at=at,askAt=at,bid=10,ask=10))
        for i,score in [('a',90),('b',89),('c',88),('d',85)]]

def cohort(at):
    return dict(at=at,slot=r.statistics.slot_at(at),marketReady=True,candidates=candidates(at),
                missing=[],chosen='a',currency='EUR',direction='LONG')

def points(row):
    return {c['isin']:[dict(isin=c['isin'],source='test',currency='EUR',at=row['at']+n*30000,
        bid=10+(index+1)*.1) for n in range(1,121)] for index,c in enumerate(row['candidates'])}

def rows(start,end,good=True,gain=.5):
    out=[]
    for i,slot in enumerate(r.timing.slots(start,end)):
        row=cohort(slot+10000);row['direction']='LONG' if i%2 else 'SHORT'
        out.append((row,dict(complete=True,returns={k:dict(grossPct=v,worstObservedPct=0) for k,v in
            dict(a=.1,b=gain if good else -.4,c=.2,d=3).items()})))
    return out

class RankingTests(unittest.TestCase):
    def selected(self):
        s=r.initial(NOW);data=rows(s['start'],s['selectionEnd'])
        return r.transition(s,data,s['selectionEnd']),data
    def adopted(self):
        s,data=self.selected();data+=rows(s['validationStart'],s['validationEnd'])
        return r.transition(s,data,s['validationEnd']+r.HOUR+60000),data
    def test_full_list_winner_is_not_retroactive_selection(self):
        row=cohort(NOW);before=copy.deepcopy(row);out=r.evaluate(row,points(row))
        self.assertTrue(out['complete']);self.assertEqual(out['bestIsins'],['d'])
        self.assertEqual(out['chosenIsin'],'a');self.assertEqual(out['alternativeIsin'],'d')
        self.assertAlmostEqual(out['alternativeAdvantagePct'],3)
        self.assertAlmostEqual(out['returns']['a']['stressPct'],.7)
        self.assertEqual(row,before);self.assertFalse(out['actualExecution'])
    def test_missing_identity_currency_source_gap_conflict_blocks_winner(self):
        row=cohort(NOW)
        for change in ({'currency':'CHF'},{'source':'other'},{'isin':'x'},{'bid':0}):
            data=points(row);data['d']=[dict(p,**change) for p in data['d']]
            out=r.evaluate(row,data);self.assertFalse(out['complete']);self.assertNotIn('bestIsins',out)
        for change in ('gap','exit','conflict','skew'):
            data=points(row)
            if change=='gap':data['d']=data['d'][4:]
            if change=='exit':data['d']=data['d'][:-1]
            if change=='conflict':data['d'].append(dict(data['d'][0],bid=999))
            if change=='skew':data['d'][-1]['at']+=31000
            self.assertFalse(r.evaluate(row,data)['complete'],change)
    def test_ties_and_negative_alternative_do_not_claim_improvement(self):
        row=cohort(NOW);data=points(row)
        data['a']=[dict(p,bid=11) for p in data['a']]
        out=r.evaluate(row,data);self.assertEqual(out['bestIsins'],['a']);self.assertLess(out['alternativeAdvantagePct'],0)
        data['d']=[dict(p,bid=11) for p in data['d']]
        self.assertEqual(r.evaluate(row,data)['bestIsins'],['a','d'])
    def test_bounded_rules_and_paper_admission(self):
        cs=candidates(NOW)
        self.assertEqual(r.choose(cs,'third')['isin'],'c')
        cs[2]['score']=84;cs[3]['score']=83;self.assertEqual(r.choose(cs,'third')['isin'],'a')
        self.assertEqual(r.choose(cs,'made-up')['isin'],'a')
        cs[0]['paperOnly']=True;self.assertEqual(r.choose(cs,'second')['isin'],'a')
        s=r.initial(NOW);data=rows(s['start'],s['selectionEnd'])
        for row,_ in data:
            for c in row['candidates']:c['paperOnly']=True
        self.assertEqual(r.metrics(data,s['start'],s['selectionEnd'],'second')['samples'],0)
    def test_disjoint_freeze_adoption_and_future_not_used_in_selection(self):
        s,data=self.selected();self.assertEqual(s['phase'],'validation');self.assertEqual(s['candidate'],'second')
        self.assertEqual(s['active'],'baseline');self.assertGreater(s['validationStart'],s['selectionEnd'])
        s,data=self.adopted();self.assertEqual(s['phase'],'monitoring');self.assertEqual(s['active'],'second')
        self.assertGreater(min(s['lowerBounds99'].values()),0)
        initial=r.initial(NOW)
        future=rows(initial['selectionEnd'],initial['selectionEnd']+42*r.DAY)
        self.assertEqual(r.transition(initial,future,initial['selectionEnd'])['phase'],'cooldown')
    def test_failed_holdout_never_refits_on_winner(self):
        s,data=self.selected();bad=rows(s['validationStart'],s['validationEnd'],False)
        # Another candidate wins the holdout but was not frozen at selection.
        for row,o in bad:o['returns']['c']['grossPct']=4
        out=r.transition(s,data+bad,s['validationEnd']+r.HOUR+60000)
        self.assertEqual(out['candidate'],'second');self.assertEqual(out['active'],'baseline')
        self.assertEqual(out['phase'],'cooldown')
    def test_costs_drawdown_single_direction_coverage_and_incomplete(self):
        s=r.initial(NOW);data=rows(s['start'],s['selectionEnd'],gain=.2)
        self.assertFalse(r.advantage(r.metrics(data,s['start'],s['selectionEnd'],'second')))
        data=rows(s['start'],s['selectionEnd'])
        m=r.metrics(data,s['start'],s['selectionEnd'],'second');self.assertTrue(r.sufficient(m));self.assertTrue(r.advantage(m))
        data[0][1]['returns']['b']['worstObservedPct']=-2
        self.assertFalse(r.advantage(r.metrics(data,s['start'],s['selectionEnd'],'second')))
        for row,_ in data:row['direction']='LONG'
        self.assertFalse(r.sufficient(r.metrics(data,s['start'],s['selectionEnd'],'second')))
        self.assertFalse(r.sufficient(r.metrics(data[::2],s['start'],s['selectionEnd'],'second')))
        data=rows(s['start'],s['selectionEnd']);data[0][1]['complete']=False
        self.assertFalse(r.sufficient(r.metrics(data,s['start'],s['selectionEnd'],'second')))
    def test_monitor_reversal_outage_and_manual_pause(self):
        s,old=self.adopted();s['lastCheckedAt']=s['monitorEnd']
        out=r.transition(s,old+rows(s['monitorStart'],s['monitorEnd'],False),s['monitorEnd']+r.HOUR+60000)
        self.assertEqual(out['active'],'baseline');self.assertEqual(out['history'][-1]['event'],'rollback')
        self.assertEqual(r.transition(s,old,s['lastCheckedAt']+2*r.DAY)['phase'],'cooldown')
        out=r.transition(s,old+rows(s['monitorStart'],s['monitorEnd']),s['monitorEnd']+r.HOUR+60000)
        self.assertEqual(out['phase'],'monitoring');self.assertGreater(out['monitorStart'],s['monitorEnd'])
        r.revert(out,NOW,'manual',True)
        self.assertEqual(r.transition(out,[],NOW+200*r.DAY)['phase'],'paused')
    def test_lease_protocol_and_effective_time_fail_closed(self):
        s,_=self.adopted();conn=Mock();conn.execute.return_value.fetchall.return_value=[('EUR',s)]
        self.assertEqual(r.policy(conn,s['effectiveAt'])['variants']['EUR'],'second')
        self.assertEqual(r.policy(conn,s['effectiveAt']-1)['variants']['EUR'],'baseline')
        self.assertEqual(r.policy(conn,s['lastCheckedAt']+180001)['variants']['EUR'],'baseline')
        s['protocol']['maxScoreGap']=99
        self.assertEqual(r.policy(conn,s['effectiveAt'])['variants']['EUR'],'baseline')

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PersistenceTests(unittest.TestCase):
    def test_immutable_capture_harvest_policy_and_restart(self):
        import psycopg,uuid
        from psycopg import sql
        schema='ranking_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                r.precision.init(conn);r.init(conn)
                at=r.timing.next_slot(NOW)+10000;cs=candidates(at)
                market=dict(ready=True,priceFresh=True,direction='LONG')
                choices=[dict(c,scope='XAU/USD') for c in cs]
                def freeze(m,c,q,spots,now):return dict(quote=c['quote'],identity={'test':True})
                quotes={c['isin']:dict(currency='EUR') for c in cs}
                with patch.object(r.precision,'freeze',side_effect=freeze):
                    r.capture(conn,market,dict(researchCandidates=choices),quotes,{},at)
                    r.capture(conn,market,dict(researchCandidates=[]),{}, {},at+1000)
                row=conn.execute("SELECT payload FROM bob_ranking_samples WHERE currency='EUR'").fetchone()[0]
                self.assertEqual(len(row['candidates']),4)
                for isin,observations in points(row).items():
                    for q in observations:conn.execute('INSERT INTO bob_precision_quotes VALUES(%s,%s,%s,%s,%s::jsonb)',(isin,'test','EUR',q['at'],json.dumps(q)))
                r.harvest(conn,at+r.HOUR+60001);r.harvest(conn,at+r.HOUR+60002)
                out=conn.execute("SELECT outcome FROM bob_ranking_samples WHERE currency='EUR'").fetchone()[0]
                self.assertEqual(out['bestIsins'],['d']);conn.commit()
                r.tick(conn,at);r.control(conn,False,at+1);conn.commit();r.init(conn)
                self.assertTrue(all(s['phase']=='paused' for s in r.report(conn,at+2)['states'].values()))
                r.control(conn,True,at+3)
                self.assertTrue(all(s['start']>at+3 for s in r.report(conn,at+4)['states'].values()))
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_ranking_events').fetchone()[0],4)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':unittest.main()
