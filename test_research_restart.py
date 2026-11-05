import copy
import json
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import Mock, patch

import research_restart as r
from test_paper_shadow_studies import observed

NOW = int(datetime(2026,11,5,10,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)


def sample(at=NOW, price=4000., direction='LONG', warning=True, adx=15.):
    b, m = observed(at, direction, price, adx)
    if warning:
        m['earlyWarning'] = dict(available=True,state='active',comparisonOnly=True,
                                affectsApproval=False,extensionRisk=False,
                                direction='LONG',signalBarAt=NOW-300000,expiresAt=NOW+7200000)
    return b,m


class Tests(unittest.TestCase):
    def test_shared_cases_and_original_inputs_unchanged(self):
        b,m=sample(); original=copy.deepcopy((b,m));state=r.seed(NOW)
        result,closed=r.advance(state,b,m,NOW)
        self.assertEqual((b,m),original)
        self.assertEqual(state['quality']['cycles'],0)
        self.assertEqual(len(closed),0)
        for ctl in result['studies'].values():
            self.assertEqual(ctl['started'],1)
            self.assertEqual(ctl['open'][0]['at'],NOW)
        self.assertTrue(result['studies']['sideways-filter']['open'][0]['legs']['filter']['wait'])

    def test_current_five_minute_signal_clock_is_not_mistaken_for_15m(self):
        b,m=sample();bar=NOW-300000
        m['analysisBarAt']=bar;m['entryTiming']='five-minute-confirmation'
        b['history']['bars_by_tf']['5m']=[dict(openTime=bar,isOpen=False)]
        state,_=r.advance(r.seed(NOW),b,m,NOW)
        self.assertEqual(state['quality']['original'],1)
        b['history']['bars_by_tf']['5m'][0]['isOpen']=True
        state,_=r.advance(r.seed(NOW),b,m,NOW)
        self.assertEqual(state['quality']['invalid'],1)

    def test_continuous_original_hour_yields_paired_results(self):
        state=r.seed(NOW);closed=[]
        for elapsed in range(0,3600001,30000):
            b,m=sample(NOW+elapsed,4000+elapsed/90000)
            state,out=r.advance(state,b,m,NOW+elapsed);closed+=out
        self.assertEqual(len(closed),3)
        self.assertTrue(all(c['status']=='complete' for c in closed))
        delay=next(c for c in closed if c['study']=='entry-delay')
        self.assertEqual(delay['legs']['30s']['entry']['at'],NOW+30000)
        self.assertEqual(delay['legs']['60s']['entry']['at'],NOW+60000)
        self.assertGreater(delay['returnsPct']['0s'],delay['returnsPct']['60s'])
        sideways=next(c for c in closed if c['study']=='sideways-filter')
        self.assertEqual(sideways['returnsPct']['filter'],0)
        self.assertAlmostEqual(sideways['returnsPct']['baseline'],.84)

    def test_gap_excludes_even_when_later_exit_is_available(self):
        b,m=sample();state,_=r.advance(r.seed(NOW),b,m,NOW)
        b,m=sample(NOW+3600000,4100)
        state,closed=r.advance(state,b,m,NOW+3600000)
        self.assertEqual(len(closed),3)
        self.assertTrue(all(c['status']=='inconclusive' and not c['returnsPct'] for c in closed))
        self.assertEqual(state['quality']['missingIntervals'],1)

    def test_duplicate_future_stale_and_estimated_do_not_open_cases(self):
        b,m=sample();state,_=r.advance(r.seed(NOW),b,m,NOW)
        again,_=r.advance(state,b,m,NOW+1000)
        self.assertEqual(again['quality']['duplicateSource'],1)
        self.assertEqual(again['studies']['entry-delay']['started'],1)
        for kind in ('future','stale','estimated'):
            b,m=sample();now=NOW
            if kind=='future':now=NOW-1
            if kind=='stale':now=NOW+61000
            if kind=='estimated':b['history']['bars_by_tf']['15m'][0]['estimated']=True
            result,_=r.advance(r.seed(now),b,m,now)
            self.assertTrue(all(c['started']==0 for c in result['studies'].values()),kind)

    def test_signal_disappears_before_delayed_entry(self):
        b,m=sample();state,_=r.advance(r.seed(NOW),b,m,NOW)
        b,m=sample(NOW+30000,direction='NEUTRAL',warning=False)
        state,_=r.advance(state,b,m,NOW+30000)
        l=state['studies']['entry-delay']['open'][0]['legs']['30s']
        self.assertTrue(l['wait']);self.assertIsNone(l['entry'])

    def test_confirmation_waits_for_observed_confirmation(self):
        b,m=sample(direction='NEUTRAL');state,_=r.advance(r.seed(NOW),b,m,NOW)
        self.assertIsNone(state['studies']['warning-confirmed']['open'][0]['legs']['confirmed']['entry'])
        b,m=sample(NOW+30000,direction='LONG')
        state,_=r.advance(state,b,m,NOW+30000)
        self.assertEqual(state['studies']['warning-confirmed']['open'][0]['legs']['confirmed']['entry']['at'],NOW+30000)

    def test_no_confirmation_is_wait_not_losing_trade(self):
        state=r.seed(NOW);closed=[]
        for elapsed in range(0,3600001,30000):
            b,m=sample(NOW+elapsed,direction='NEUTRAL')
            state,out=r.advance(state,b,m,NOW+elapsed);closed+=out
        c=next(c for c in closed if c['study']=='warning-confirmed')
        self.assertEqual(c['returnsPct']['confirmed'],0.)

    def test_deadline_finishes_missing_cases_without_inventing_prices(self):
        b,m=sample();state,_=r.advance(r.seed(NOW),b,m,NOW)
        state['deadlineAt']=NOW+1000
        state,closed=r.advance(state,b,m,NOW+3600000+60001)
        self.assertEqual(state['status'],'completed-review-required')
        self.assertTrue(all(c['status']=='inconclusive' for c in closed))
        after,out=r.advance(state,b,m,NOW+7200000)
        self.assertEqual(after,state);self.assertFalse(out)

    def test_retirement_overrides_old_campaign_extension(self):
        import paper_simulation as p
        ctl=dict(startAt=NOW-86400000,retiredAt=NOW-1000,enabled=True,status='running')
        conn=Mock()
        conn.execute.return_value.fetchone.side_effect=[(ctl,),None]
        with patch.object(p.background_push,'degiro_session',return_value='trading'):
            p.run_once(conn,{}, {}, {'choices':[]},{},NOW,{'campaign_end':NOW+86400000})
        self.assertEqual(ctl['status'],'completed')
        self.assertEqual(ctl['endAt'],NOW-1000)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_atomic_idempotent_snapshot_and_restart(self):
        import uuid
        import psycopg
        from psycopg import sql
        import paper_portfolios as p
        import risk_paper
        import paper_shadow_studies as shadow
        schema='quality_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)));conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                p.init(conn);risk_paper.init(conn);shadow.init(conn);r.init(conn)
                before=conn.execute('SELECT payload FROM bob_paper_balanced_control').fetchone()[0]
                conn.commit()
                r.start(conn,NOW)
                # A transaction rollback must undo snapshots AND retire flags.
                conn.rollback()
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_quality_legacy').fetchone()[0],0)
                self.assertNotIn('retiredAt',conn.execute('SELECT payload FROM bob_paper_balanced_control').fetchone()[0])
                r.start(conn,NOW);conn.commit()
                r.start(conn,NOW+1000)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_quality_legacy').fetchone()[0],11)
                archived=conn.execute('SELECT payload FROM bob_quality_legacy WHERE id=%s',(r.VERSION+':paper-balanced',)).fetchone()[0]
                self.assertNotIn('retiredAt',archived)
                self.assertEqual(archived['cash'],before['cash'])
                ctl=conn.execute('SELECT payload FROM bob_paper_balanced_control').fetchone()[0]
                self.assertEqual(ctl['retiredAt'],NOW)
                b,m=sample();r.tick(conn,b,m,NOW)
                result=r.report(conn)
                self.assertEqual(len(result['studies']),4)
                self.assertFalse(result['liveRulesChanged'])
                self.assertEqual(result['legacySnapshots'],11)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)));conn.commit()


if __name__=='__main__':unittest.main()
