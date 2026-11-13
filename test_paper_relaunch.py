"""Second, forward-only Bob virtual comparison: independent 800/1000 EUR ledgers."""
import copy
import json
import os
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import paper_portfolios as profiles
import paper_simulation as simulation
import paper_profit_summary
from test_bob_stop_reentry import MemoryLedger
from test_trend_follow import market


class NovemberRelaunchTests(unittest.TestCase):
    PROFILES = ('trend800nov', 'normal1000nov')

    def test_common_market_window_and_unchanged_parent_risk(self):
        self.assertEqual(profiles.RELAUNCH_START, int(datetime(
            2026, 11, 9, 8, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000))
        self.assertEqual(profiles.RELAUNCH_END, int(datetime(
            2026, 12, 4, 16, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000))
        self.assertNotEqual(profiles.names('trend800nov'), profiles.names('trend800'))
        self.assertNotEqual(profiles.names('normal1000nov'), profiles.names('normal1000oct'))
        self.assertNotEqual(profiles.names('trend800nov'), profiles.names('normal1000nov'))
        for name, parent in [('trend800nov','trend800'),('normal1000nov','normal1000oct')]:
            p, previous = profiles.POLICIES[name], profiles.POLICIES[parent]
            self.assertTrue(p['campaign'])
            self.assertTrue(p['relaunch'])
            self.assertEqual(p['campaign_id'], profiles.RELAUNCH_ID)
            self.assertEqual(p['start_at'], profiles.RELAUNCH_START)
            self.assertEqual(p['campaign_end'], profiles.RELAUNCH_END)
            for field in ('initial_capital_eur','exposure_fraction','daily_loss_fraction',
                          'score_long','score_short','require_trend'):
                self.assertEqual(p[field], previous[field])
            self.assertEqual(p.get('bob_stop_reentry'), previous.get('bob_stop_reentry'))
            self.assertEqual(p.get('early_warning'), previous.get('early_warning'))
            self.assertEqual(p['exposure_fraction'], .65)
            self.assertEqual(p['daily_loss_fraction'], .03)
        self.assertFalse(hasattr(profiles,'place_order'))

    def test_future_start_is_seeded_without_resetting_old_controls(self):
        class Capture:
            def __init__(self):
                self.seeds = {}
                self.statements = []
            def execute(self, sql, params=()):
                self.statements.append(sql)
                for profile in profiles.POLICIES:
                    table = profiles.names(profile)['bob_paper_control']
                    if sql.startswith('INSERT INTO '+table+' (id,payload)'):
                        self.seeds[profile] = json.loads(params[0])
                return self
        conn = Capture()
        with patch('paper_portfolios.time.time',return_value=datetime(
                2026,11,7,4,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()):
            profiles.init(conn)
        self.assertEqual(len(conn.seeds),len(profiles.POLICIES))
        for name, capital in [('trend800nov',800.),('normal1000nov',1000.)]:
            saved=conn.seeds[name]
            self.assertEqual(saved['status'],'scheduled')
            self.assertTrue(saved['enabled'])
            self.assertEqual(saved['startAt'],profiles.RELAUNCH_START)
            self.assertEqual(saved['endAt'],profiles.RELAUNCH_END)
            self.assertEqual(saved['campaign'],profiles.RELAUNCH_ID)
            self.assertEqual(saved['cash'],capital)
            self.assertEqual(saved['equity'],capital)
            self.assertEqual(saved['totalProfit'],0.)
        self.assertNotEqual(conn.seeds['trend800nov']['startAt'],
                            conn.seeds['trend800']['startAt'])
        self.assertNotEqual(conn.seeds['normal1000nov']['campaign'],
                            conn.seeds['normal1000oct']['campaign'])
        self.assertTrue(all('ON CONFLICT DO NOTHING' in s
                            for s in conn.statements if s.startswith('INSERT INTO bob_paper_')))

    def test_no_entry_before_monday_even_with_signal_and_selection(self):
        saturday=int(datetime(2026,11,7,12,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
        for name in self.PROFILES:
            ledger=MemoryLedger()
            capital=profiles.POLICIES[name]['initial_capital_eur']
            ledger.control.update(status='scheduled',startAt=profiles.RELAUNCH_START,
                                  endAt=profiles.RELAUNCH_END,initialCapital=capital,
                                  cash=capital,equity=capital)
            snapshot=copy.deepcopy(ledger.control)
            with patch('paper_simulation.new_case') as new_case:
                simulation.run_once(ledger,{},market(at=saturday),{'choices':[{'isin':'TEST'}]},
                                    {},saturday,profiles.POLICIES[name])
                new_case.assert_not_called()
            self.assertEqual(ledger.control['status'],'scheduled')
            self.assertIsNone(ledger.active)
            self.assertEqual(ledger.control['cash'],snapshot['cash'])
            self.assertEqual(ledger.control['equity'],snapshot['equity'])
            self.assertIn('09.11.2026',ledger.control['reason'])

    def test_comparison_will_not_claim_proven_winner(self):
        def row(name,initial,equity,closed=3,priced=3,unknown=0,status='completed'):
            return dict(profile=name,
                        control=dict(status=status,startAt=profiles.RELAUNCH_START,
                          endAt=profiles.RELAUNCH_END,initialCapital=initial,equity=equity,
                          totalProfit=equity-initial,costsDebitedEur=4),
                        performance=dict(closedTrades=closed,pricedTrades=priced,
                          inconclusiveTrades=unknown,observedMaxDrawdownPct=7.))
        original=[
            row('trend800nov',800.,880.),
            row('normal1000nov',1000.,1090.),
        ]
        x=profiles.relaunch_comparison(original)
        self.assertEqual(x['modelReturnDifferenceTrendMinusMainPctPoints'],1.)
        self.assertEqual(x['status'],'completed-model-comparison-only')
        self.assertTrue(x['comparableModelClosures'])
        self.assertFalse(x['strategyWinnerConfirmed'])
        self.assertFalse(x['brokerNetVerified'])
        for change in ({'inconclusiveTrades':1},{'pricedTrades':2},{'closedTrades':0}):
            bad=copy.deepcopy(original)
            bad[0]['performance'].update(change)
            z=profiles.relaunch_comparison(bad)
            self.assertIsNone(z['modelReturnDifferenceTrendMinusMainPctPoints'])
            self.assertEqual(z['status'],'completed-insufficient-evidence')
        self.assertFalse(profiles.relaunch_comparison([])['strategyWinnerConfirmed'])
        self.assertIsNone(profiles.relaunch_comparison([])['modelReturnDifferenceTrendMinusMainPctPoints'])
        self.assertEqual(original[0]['control']['equity'],880.)

    def test_private_summary_includes_new_accounts_without_profit_approval(self):
        controls=[{'profile':name,'initialCapital':capital,'cash':capital,
                   'equity':capital,'status':'scheduled','startAt':profiles.RELAUNCH_START}
                  for name,capital in [('trend800nov',800),('normal1000nov',1000)]]
        out=paper_profit_summary.snapshot(controls)
        self.assertEqual(out['status'],'partial')
        self.assertFalse(out['strategyWinnerConfirmed'])
        self.assertFalse(out['netProductReturnsVerified'])
        for profile in self.PROFILES:
            row=next(x for x in out['rows'] if x['profile']==profile)
            self.assertEqual(row['modelReturnPct'],0.)
            self.assertEqual(row['status'],'scheduled')


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                     'PostgreSQL acceptance runs in full CI')
class RelaunchDatabaseTests(unittest.TestCase):
    def test_new_tables_begin_empty_and_second_initialization_is_idempotent(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            simulation.init(conn)
            observations={}
            for profile in ('trend800','normal1000oct','trend800nov','normal1000nov'):
                table=profiles.names(profile)
                observations[profile]=conn.execute(
                    'SELECT payload FROM '+table['bob_paper_control']+' WHERE id=1').fetchone()[0]
            for profile,capital in [('trend800nov',800.),('normal1000nov',1000.)]:
                saved=observations[profile]
                self.assertEqual(saved['startAt'],profiles.RELAUNCH_START)
                self.assertEqual(saved['endAt'],profiles.RELAUNCH_END)
                self.assertEqual(saved['initialCapital'],capital)
                count=conn.execute('SELECT count(*) FROM '+
                    profiles.names(profile)['bob_paper_cases']).fetchone()[0]
                self.assertEqual(count,0)
            simulation.init(conn)
            for profile in observations:
                table=profiles.names(profile)
                self.assertEqual(conn.execute('SELECT payload FROM '+
                    table['bob_paper_control']+' WHERE id=1').fetchone()[0],
                    observations[profile])
            conn.rollback()


if __name__=='__main__':
    unittest.main()
