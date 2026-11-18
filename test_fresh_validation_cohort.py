"""Fresh, equal-capital, forward-only validation of three historically positive paper hypotheses."""
import copy
import json
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import paper_portfolios as profiles
import paper_profit_summary as summary
import paper_simulation as simulation
from test_bob_stop_reentry import MemoryLedger


def ch_ms(year, month, day, hour, minute=0):
    return int(datetime(year,month,day,hour,minute,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)


class FreshValidationCohortTests(unittest.TestCase):
    ARMS = ('trend1000dec', 'normal1000dec', 'early1000dec')
    PARENTS = ('trend800', 'normal1000oct', 'early1000oct')

    def test_three_isolated_equal_capital_paper_policies_are_frozen(self):
        self.assertEqual(profiles.FRESH_VALIDATION_PROFILES, self.ARMS)
        self.assertEqual(profiles.FRESH_VALIDATION_NOT_BEFORE,ch_ms(2026,11,17,8))
        self.assertEqual(profiles.FRESH_VALIDATION_END,ch_ms(2026,12,15,16))
        self.assertEqual(len(profiles.POLICIES),15)
        self.assertNotIn('early5m1000nov',self.ARMS,
                         'New forward trial must never rewrite the frozen three-way cohort')
        table_sets=[]
        for name,parent in zip(self.ARMS,self.PARENTS):
            p=profiles.POLICIES[name]
            original=profiles.POLICIES[parent]
            self.assertEqual(p['initial_capital_eur'],1000.)
            self.assertEqual(p['campaign_id'],profiles.FRESH_VALIDATION_ID)
            self.assertTrue(p['campaign'])
            self.assertTrue(p['fresh_validation'])
            self.assertFalse(p['relaunch'])
            self.assertEqual(p['campaign_end'],profiles.FRESH_VALIDATION_END)
            self.assertFalse(p.get('paper_campaign_entry',False),
                             'do not silently promote experimental November entry gates')
            for key in ('exposure_fraction','daily_loss_fraction','score_long',
                        'score_short','require_trend','early_warning','bob_stop_reentry'):
                self.assertEqual(p.get(key), original.get(key))
            self.assertEqual(p['exposure_fraction'],.65)
            self.assertEqual(p['daily_loss_fraction'],.03)
            table_sets.append(tuple(profiles.names(name).values()))
            self.assertIn(name,summary.PROFILES)
        self.assertEqual(len(set(table_sets)),3)
        for old in self.PARENTS:
            self.assertNotIn(tuple(profiles.names(old).values()),table_sets)
        self.assertFalse(hasattr(profiles,'place_order'))

    def test_common_true_start_and_no_reset_or_backfill(self):
        class Capture:
            def __init__(self):
                self.seeded={}
                self.writes=[]
            def execute(self,sql,params=()):
                self.writes.append(sql)
                for name in profiles.POLICIES:
                    table=profiles.names(name)['bob_paper_control']
                    if sql.startswith('INSERT INTO '+table+' (id,payload)'):
                        self.seeded[name]=json.loads(params[0])
                return self
        for started in (ch_ms(2026,11,12,12),ch_ms(2026,11,18,9,10)):
            capture=Capture()
            with patch('paper_portfolios.time.time',return_value=started/1000):
                profiles.init(capture)
            saved=[capture.seeded[n] for n in self.ARMS]
            actual=max(started, profiles.FRESH_VALIDATION_NOT_BEFORE)
            self.assertEqual([x['startAt'] for x in saved],[actual]*3)
            self.assertEqual([x['initialCapital'] for x in saved],[1000.]*3)
            self.assertEqual([x['cash'] for x in saved],[1000.]*3)
            self.assertEqual([x['equity'] for x in saved],[1000.]*3)
            self.assertEqual([x['totalProfit'] for x in saved],[0.]*3)
            self.assertTrue(all(x['status']=='scheduled' and
                x['endAt']==profiles.FRESH_VALIDATION_END for x in saved))
            for p in self.PARENTS:
                self.assertNotEqual(capture.seeded[p].get('campaign'),
                                    profiles.FRESH_VALIDATION_ID)
            self.assertTrue(all('ON CONFLICT DO NOTHING' in x
                for x in capture.writes if x.startswith('INSERT INTO bob_paper_')))

    def test_no_fictitious_entry_before_prospective_start(self):
        old=ch_ms(2026,11,16,14)
        for profile in self.ARMS:
            ledger=MemoryLedger()
            ledger.control.update(startAt=profiles.FRESH_VALIDATION_NOT_BEFORE,
                status='scheduled',cash=1000.,equity=1000.,initialCapital=1000.,
                endAt=profiles.FRESH_VALIDATION_END)
            before=copy.deepcopy(ledger.control)
            with patch('paper_simulation.new_case') as new_case:
                simulation.run_once(ledger,{},dict(direction='LONG',ready=True),
                    dict(choices=[]),{},old,profiles.POLICIES[profile])
            new_case.assert_not_called()
            self.assertIsNone(ledger.active)
            self.assertEqual(ledger.control['status'],'scheduled')
            self.assertEqual(ledger.control['cash'],before['cash'])
            self.assertEqual(ledger.control['equity'],before['equity'])

    def test_positive_model_numbers_never_confirm_winner(self):
        common=ch_ms(2026,11,18,9,10)
        def row(p,priced=0,closed=0,unknown=0,status='running',start=None):
            return dict(profile=p,control=dict(status=status,
                startAt=common if start is None else start,
                endAt=profiles.FRESH_VALIDATION_END,
                initialCapital=1000.,equity=1120.,totalProfit=120.),
                performance=dict(closedTrades=closed,pricedTrades=priced,
                    inconclusiveTrades=unknown,observedMaxDrawdownPct=3.5))
        rows=[row(p) for p in self.ARMS]
        s=profiles.fresh_validation_comparison(rows)
        self.assertEqual(s['status'],'running-or-paused')
        self.assertTrue(s['sameStartVerified'])
        self.assertFalse(s['reviewEligible'])
        self.assertFalse(s['strategyWinnerConfirmed'])
        self.assertFalse(s['brokerNetVerified'])
        self.assertFalse(s.get('realOrders'))
        self.assertEqual(len(s['accounts']),3)
        enough=[row(p,20,20,0,'completed') for p in self.ARMS]
        complete=profiles.fresh_validation_comparison(enough)
        self.assertEqual(complete['status'],'completed-review-required')
        self.assertTrue(complete['reviewEligible'])
        self.assertFalse(complete['strategyWinnerConfirmed'])
        self.assertFalse(complete['brokerNetVerified'])
        for change in ('no-closures','missing-bid','unresolved','unequal-start'):
            data=copy.deepcopy(enough)
            if change=='no-closures':data[0]['performance']['closedTrades']=0
            if change=='missing-bid':data[0]['performance']['pricedTrades']=19
            if change=='unresolved':data[0]['performance']['inconclusiveTrades']=1
            if change=='unequal-start':data[0]['control']['startAt']+=30000
            result=profiles.fresh_validation_comparison(data)
            self.assertEqual(result['status'],'completed-insufficient-evidence')
            self.assertFalse(result['reviewEligible'])

    def test_diagnostics_keep_results_distinct_from_historical_profits(self):
        controls=[dict(profile=p,initialCapital=1000.,cash=1000.,equity=1000.,
            totalProfit=0.,status='running',lastTradingEntryBlockCode='no-direction',
            lastTradingEntryBlockAt=ch_ms(2026,11,18,10))
            for p in self.ARMS]
        result=summary.snapshot(controls)
        self.assertFalse(result['strategyWinnerConfirmed'])
        self.assertFalse(result['netProductReturnsVerified'])
        self.assertEqual([next(a for a in result['rows'] if a['profile']==p)['modelReturnPct']
                          for p in self.ARMS],[0.,0.,0.])
        for p in self.ARMS:
            row=next(a for a in result['rows'] if a['profile']==p)
            self.assertEqual(row['latestEntryBlockCode'],'no-direction')


if __name__ == '__main__':
    unittest.main()
