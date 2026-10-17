import copy
import json
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import ranking_learning as rank
import ranking_lifecycle as life
import ranking_regimes as regimes
import paper_simulation as sim
from test_ranking_learning import rows
from test_paper_ko_guard import market,quote,choice,NOW,ISIN

class ExitTests(unittest.TestCase):
    def state(self):
        m=market();q=quote(ko=3500.)
        c=sim.new_case(m,choice(),q,NOW,cash=life.CAPITAL);c['comparisonLastQuoteAt']=NOW
        return dict(cases={ISIN:c},missing=[]),m,q
    def test_same_real_engine_stop_target_partial_trailing_and_reversal(self):
        for prices in ([3790.],[4310.,4360.,4100.],[4010.]):
            state,m,q=self.state();expected=copy.deepcopy(state['cases'][ISIN])
            for i,price in enumerate(prices,1):
                at=NOW+i*30000;tick={**m,'price':price,'dataAt':at,'analysisBarAt':at}
                if prices==[4010.]:tick['direction']='SHORT'
                tickq=quote(at,ko=3500.,bid=10+i*.5)
                expected=sim.advance_case(expected,tick,tickq,at)
                state=life.advance_state(state,tick,{ISIN:tickq},at)
                actual=state['cases'][ISIN]
                self.assertEqual(actual['events'],expected['events'])
                self.assertEqual(actual['engine'],expected['engine'])
                self.assertEqual(actual['cashReleased'],expected['cashReleased'])
                self.assertEqual(actual['status'],expected['status'])
    def test_quote_source_gap_missing_and_gold_gap_cannot_become_winner(self):
        for mode in ('source','missing','product-gap','gold-gap','zero'):
            state,m,q=self.state();at=NOW+(120000 if mode in ('product-gap','gold-gap') else 30000)
            tick={**m,'dataAt':at,'price':3790.};tickq=quote(at,ko=3500.)
            if mode=='source':tickq['source']='other'
            if mode=='missing':tickq=None
            if mode=='zero':tickq['bid']=0
            if mode=='gold-gap':state['cases'][ISIN]['comparisonLastQuoteAt']=at-30000
            out=life.advance_state(state,tick,{ISIN:tickq},at)['cases'][ISIN]
            self.assertEqual(out['status'],'inconclusive',mode);self.assertFalse(out['productReturnKnown'])
    def test_terminal_ko_and_missing_guard_never_invent_sale(self):
        state,m,q=self.state();at=NOW+30000
        for tickq in (quote(at,status=2),{**quote(at),'conditions':{}}):
            out=life.advance_state(state,{**m,'dataAt':at},{ISIN:tickq},at)['cases'][ISIN]
            self.assertEqual(out['status'],'inconclusive');self.assertFalse(out['productReturnKnown'])
    def test_same_capital_and_all_candidates_required(self):
        state,m,q=self.state();c=state['cases'][ISIN]
        c.update(status='closed',productReturnKnown=True,cashReleased=110.,allocated=90.,closedAt=NOW+30000,exitReason='stop')
        second=copy.deepcopy(c);second.update(cashReleased=108.,allocated=80.)
        state['cases']['second']=second
        row=dict(candidates=[dict(isin=ISIN),dict(isin='second')],chosen=ISIN)
        result=life.summarize(row,state)
        self.assertTrue(result['complete']);self.assertEqual(result['bestIsins'],['second'])
        self.assertEqual(result['returns'][ISIN]['grossPct'],20.)
        self.assertAlmostEqual(result['alternativeAdvantagePct'],8.)
        state['cases']['second']['status']='inconclusive'
        result=life.summarize(row,state);self.assertFalse(result['complete']);self.assertNotIn('bestIsins',result)

class RegimeTests(unittest.TestCase):
    def test_boundaries_unknown_and_frozen_inputs(self):
        m=dict(ready=True,priceFresh=True,price=100.,context=dict(adx=25.,atr=.3),dataAt=NOW)
        before=copy.deepcopy(m);out=regimes.classify(m)
        self.assertEqual((out['trend'],out['volatility']),('strong-trend','high'));self.assertEqual(m,before)
        m['context'].update(adx=19.9,atr=.099)
        self.assertEqual(regimes.classify(m)['trend'],'sideways');self.assertEqual(regimes.classify(m)['volatility'],'low')
        self.assertEqual(regimes.classify(dict(m,priceFresh=False))['trend'],'unknown')
        m['context']['adx']=float('nan');self.assertIsNone(regimes.classify(m)['adx'])
        self.assertEqual(out['trend'],'strong-trend','Later market never relabels frozen entry')
    def test_currency_missing_and_exit_groups_are_separate(self):
        r=dict(slot=NOW,currency='EUR',regime={'trend':'sideways','volatility':'low'})
        o=dict(complete=True,chosenPct=1,bestPct=3)
        out=regimes.summarize([(r,o),(dict(r,currency='CHF'),None)],
            [dict(currency='EUR',slot=NOW,complete=True,chosenPct=2,bestPct=4)])
        self.assertTrue(out['descriptiveOnly']);self.assertEqual(len(out['groups']),2)
        self.assertEqual(out['groups'][0]['exitChosenMeanPct'],2)
        self.assertEqual(out['groups'][1]['horizonCount'],0)

class EarlyTests(unittest.TestCase):
    def setup_monitor(self):
        start=int(datetime(2026,10,19,8,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        end=int(datetime(2026,10,22,0,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        s=rank.initial(start-1);s.update(phase='monitoring',active='second',candidate='second',monitorStart=start,monitorEnd=start+7*rank.DAY,lastCheckedAt=end)
        data=rows(start,end,False)
        for _,o in data:o['returns']['b']['worstObservedPct']=-.5
        return s,data,end
    def test_early_rollback_before_weekly_deadline(self):
        s,data,end=self.setup_monitor();out=rank.transition(s,data,end)
        self.assertLess(end,s['monitorEnd']);self.assertEqual(out['active'],'baseline')
        self.assertTrue(out['earlyReview']['triggered']);self.assertIn('earlyEvidence',out['history'][-1])
    def test_single_loss_two_days_missing_and_future_do_not_trigger(self):
        s,data,end=self.setup_monitor()
        for variant in ('one-loss','two-days','missing','future'):
            test=copy.deepcopy(data)
            if variant=='one-loss':
                for _,o in test[1:]:o['returns']['b'].update(grossPct=.5,worstObservedPct=0)
            if variant=='two-days':test=test[:12]
            if variant=='missing':test=test[::2]
            if variant=='future':
                test=[(dict(row,slot=row['slot']+7*rank.DAY),o) for row,o in test]
            out=rank.transition(s,test,end)
            self.assertEqual(out['active'],'second',variant)
    def test_checkpoint_once_daily_and_no_new_regime_rule(self):
        s,data,end=self.setup_monitor()
        for _,o in data:o['returns']['b'].update(grossPct=.5,worstObservedPct=0)
        out=rank.transition(s,data,end)
        review=copy.deepcopy(out['earlyReview'])
        again=rank.transition(out,[],end+1000)
        self.assertEqual(again['earlyReview'],review);self.assertEqual(again['active'],'second')

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PersistenceTests(unittest.TestCase):
    def test_forward_capture_tick_report_restart_and_immutable_entry(self):
        import psycopg,uuid
        from psycopg import sql
        schema='rank_exits_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            try:
                life.init(conn)
                cs=[choice(),dict(choice(),isin='second')]
                qs={ISIN:quote(ko=3500.),'second':dict(quote(ko=3500.),isin='second')}
                row=dict(currency='EUR',slot=NOW,chosen=ISIN,candidates=cs,missing=[])
                life.capture(conn,row,market(),cs,qs,NOW);conn.commit()
                self.assertEqual(life.active_isins(conn),[ISIN,'second'])
                life.capture(conn,row,market(),[],{},NOW+1)
                self.assertEqual(len(conn.execute('SELECT state FROM bob_ranking_lifecycles').fetchone()[0]['cases']),2)
                at=NOW+30000;tick={**market(),'dataAt':at,'price':3790.}
                qs={ISIN:quote(at,ko=3500.,bid=9),'second':dict(quote(at,ko=3500.,bid=9.5),isin='second')}
                life.tick(conn,tick,qs,at);conn.commit();life.init(conn)
                report=life.report(conn)['comparisons'][0]
                self.assertTrue(report['complete']);self.assertEqual(report['bestIsins'],['second'])
                self.assertEqual(life.active_isins(conn),[])
                life.tick(conn,tick,{},at+30000)
                self.assertEqual(life.report(conn)['comparisons'][0],report)
            finally:
                conn.rollback();conn.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

if __name__=='__main__':unittest.main()
