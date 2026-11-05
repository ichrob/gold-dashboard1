import copy
import unittest
from unittest.mock import patch
import paper_entry_exit_comparison as study
import paper_shadow_studies as shared
from test_paper_shadow_studies import observed
from test_paper_ko_guard import NOW, ISIN, quote, choice


class ComparisonTests(unittest.TestCase):
    def setup_case(self,direction='LONG'):
        b,m=observed(direction=direction)
        q=shared.original_input(b,m,NOW)
        return study.seed(m,q,NOW,direction),b,m

    def run_at(self,s,b,m,t=NOW,bid=10.,quotes=True):
        b=copy.deepcopy(b);m=copy.deepcopy(m)
        from datetime import datetime,timezone
        b['spots']['spot_price_as_of']=datetime.fromtimestamp(t/1000,timezone.utc).isoformat()
        m['dataAt']=t;b['spots']['xaus']=m['price']
        w={**m,'paperEntrySource':'early-warning-paper-v2'}
        direction=s['direction'];ko=3900. if direction=='LONG' else 4100.
        return study.advance(s,b,m,{'choices':[choice(direction)]},w,{'choices':[choice(direction)]},
                             {ISIN:quote(t,ko=ko,side=direction,bid=bid)} if quotes else {},t)

    def test_matrix_same_entry_for_two_exits_and_delays(self):
        s,b,m=self.setup_case();s=self.run_at(s,b,m)
        self.assertEqual(len(s['arms']),18)
        self.assertEqual(s['arms']['early:fixed:0']['entryAsk'],s['arms']['early:trailing:0']['entryAsk'])
        self.assertEqual(s['arms']['early:fixed:30']['status'],'pending')
        s=self.run_at(s,b,m,NOW+30000)
        self.assertEqual(s['arms']['early:fixed:30']['status'],'open')
        self.assertEqual(s['arms']['early:fixed:60']['status'],'pending')
        s=self.run_at(s,b,m,NOW+60000)
        self.assertEqual(s['arms']['early:fixed:60']['status'],'open')

    def test_target_only_exits_fixed_and_quote_gap_is_not_profit(self):
        s,b,m=self.setup_case();s=self.run_at(s,b,m)
        m['price']=4310.
        s=self.run_at(s,b,m,NOW+30000,bid=12.)
        self.assertEqual(s['arms']['confirmed:fixed:0']['status'],'closed')
        self.assertEqual(s['arms']['confirmed:trailing:0']['status'],'open')
        self.assertGreater(s['arms']['confirmed:fixed:0']['modelNetEur'],0)
        s=self.run_at(s,b,m,NOW+130000,quotes=False)
        self.assertEqual(s['arms']['confirmed:trailing:0']['status'],'inconclusive')
        self.assertIsNone(s['arms']['confirmed:trailing:0']['modelNetEur'])

    def test_short_target_and_opposite_direction(self):
        s,b,m=self.setup_case('SHORT');s=self.run_at(s,b,m)
        m['price']=3690.
        s=self.run_at(s,b,m,NOW+30000,bid=12.)
        self.assertEqual(s['arms']['confirmed:fixed:0']['status'],'closed')
        self.assertEqual(s['arms']['confirmed:trailing:0']['status'],'open')

    def test_no_stale_or_future_or_estimated_fill(self):
        s,b,m=self.setup_case()
        for change in ('estimated','future','missing'):
            bad=copy.deepcopy(b)
            if change=='estimated':bad['history']['bars_by_tf']['15m'][0]['estimated']=True
            if change=='future':m={**m,'dataAt':NOW+60000}
            if change=='missing':bad['spots']['xaus']=None
            out=study.advance(s,bad,m,{'choices':[choice()]},m,{}, {ISIN:quote()},NOW)
            self.assertFalse(any(a['status']=='open' for a in out['arms'].values()))

    def test_pullback_closed_bars_only_and_trailing_never_loosened(self):
        s,b,m=self.setup_case();s=self.run_at(s,b,m)
        bars=[dict(instrument='XAU/USD',openTime=NOW+i*300000,isOpen=False,
                   open=4000.,close=4001.,high=4010.,low=low)
              for i,low in enumerate((3990.,3980.,3995.))]
        b['history']['bars_by_tf']['5m']=bars
        # Continuous original monitoring until pivot confirmation.
        for i in range(1,31):s=self.run_at(s,b,m,NOW+i*30000)
        a=s['arms']['confirmed:trailing:0']
        self.assertEqual(a['stop'],3980.)
        self.assertEqual(s['arms']['confirmed:fixed:0']['stop'],3800.)
        for bar in bars:bar['low']-=100
        s=self.run_at(s,b,m,NOW+930000)
        self.assertEqual(s['arms']['confirmed:trailing:0']['stop'],3980.)
        bars[1].update(close=3990.,high=4000.)
        bars[2].update(close=4005.)
        self.assertTrue(study.pullback(b,'LONG',NOW+900000,NOW))
        bars[-1]['isOpen']=True
        self.assertFalse(study.pullback(b,'LONG',NOW+900000,NOW))

    def test_missing_entry_is_not_zero_return_and_inputs_unchanged(self):
        s,b,m=self.setup_case();original=copy.deepcopy((s,b,m))
        out=self.run_at(s,b,m,quotes=False)
        self.assertEqual((s,b,m),original)
        out=self.run_at(out,b,m,NOW+study.WINDOW,quotes=False)
        self.assertTrue(out['complete'])
        self.assertTrue(all(a['status']=='no-entry' for a in out['arms'].values()))
        self.assertTrue(all('modelNetEur' not in a for a in out['arms'].values()))

    def test_pending_exit_requires_new_bid_after_delay(self):
        s,b,m=self.setup_case();s=self.run_at(s,b,m)
        s=self.run_at(s,b,m,NOW+60000)
        m['price']=4310.
        s=self.run_at(s,b,m,NOW+90000,bid=12.)
        self.assertEqual(s['arms']['early:fixed:60']['status'],'exit-pending')
        s=self.run_at(s,b,m,NOW+120000,bid=12.)
        self.assertEqual(s['arms']['early:fixed:60']['status'],'exit-pending')
        s=self.run_at(s,b,m,NOW+150000,bid=12.)
        self.assertEqual(s['arms']['early:fixed:60']['status'],'closed')

import os

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DatabaseTests(unittest.TestCase):
    def test_persistence_restart_and_duplicate_tick(self):
        import uuid
        import psycopg
        from psycopg import sql
        schema='entry_exit_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                study.init(conn)
                b,m=observed()
                w={**m,'paperEntrySource':'early-warning-paper-v2'}
                for _ in range(2):
                    study.tick(conn,b,m,{'choices':[choice()]},w,{'choices':[choice()]},{ISIN:quote()},NOW)
                    conn.commit()
                self.assertEqual(study.active_isins(conn),[ISIN])
                report=study.report(conn)
                self.assertEqual(report['episodesSampled'],1)
                self.assertEqual(report['variants']['early:fixed:0']['open'],1)
                self.assertFalse(report['strategyWinnerConfirmed'])
                self.assertEqual(len(report['variants']),18)
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                conn.commit()

if __name__=='__main__':unittest.main()
