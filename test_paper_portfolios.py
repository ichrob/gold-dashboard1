"""Regression tests for five isolated Monday paper accounts (no real orders)."""
import json
import os
import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

import paper_portfolios as profiles
import paper_simulation as sim

NOW = int(datetime(2026, 10, 12, 9, 0, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
ISIN = 'DE000PJ9NCK0'


def market(score=82, direction='LONG'):
    return dict(plan=dict(kind='candidate', direction=direction, entry=4000.,
                          stop=3980., target=4040., unit='USD/oz'),
                price=4000., priceFresh=True, ready=True, dataAt=NOW,
                analysisBarAt=NOW, ruleVersion='forward-paper-three-test',
                direction=direction, score=score, session={'entryAllowed':True},
                trendContext=dict(available=True, intact=True,direction=direction))


def quote(at=NOW):
    return dict(isin=ISIN, found=True, marketOpen=True,
                currency='EUR', source='issuer-test',
                bid=10., ask=10.1, bidAt=at, askAt=at)


class ProfileTests(unittest.TestCase):
    def test_four_100_and_one_800_eur_accounts(self):
        self.assertEqual(list(profiles.POLICIES),
                         ['conservative','balanced','offensive','early100','trend800','early1000oct','normal1000oct'])
        self.assertEqual(len(set(profiles.names(p)['bob_paper_cases']
                                 for p in profiles.POLICIES)),7)
        self.assertEqual(profiles.START, int(datetime(
            2026,10,12,8,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000))
        self.assertFalse(hasattr(profiles, 'place_order'))

    def test_scoring_and_trend_gates(self):
        strict=profiles.POLICIES['conservative']
        regular=profiles.POLICIES['balanced']
        aggressive=profiles.POLICIES['offensive']
        self.assertIsNone(profiles.entry_block_reason(strict,market()))
        self.assertIsNotNone(profiles.entry_block_reason(strict,market(72)))
        self.assertIsNone(profiles.entry_block_reason(regular,market(72)))
        self.assertIsNotNone(profiles.entry_block_reason(regular,market(67)))
        self.assertIsNone(profiles.entry_block_reason(aggressive,market(67)))
        trendless=market()
        trendless['trendContext']['intact']=False
        self.assertIsNotNone(profiles.entry_block_reason(strict,trendless))
        self.assertIsNone(profiles.entry_block_reason(regular,trendless))


    def test_symmetric_early_shadow_gate_and_no_main_signal_change(self):
        for side in ('LONG','SHORT'):
            m=market(50,'NEUTRAL')
            m.update(ruleVersion='intraday-trend-follow-v7',
                     earlyImpulse=dict(version='early-impulse-v1',direction=side,
                         available=True,comparisonOnly=True,affectsApproval=False,
                         extensionRisk=False,barAt=NOW-300000),
                     earlyPaperPlan=dict(kind='candidate',direction=side,entry=4000.,
                         stop=4020. if side=='SHORT' else 3980.,
                         target=3960. if side=='SHORT' else 4040.,unit='USD/oz'))
            early=profiles.early_paper_market(m,NOW)
            self.assertEqual(early['direction'],side)
            self.assertEqual(early['plan']['direction'],side)
            self.assertEqual(early['paperEntrySource'],'early-impulse-paper-v1')
            self.assertEqual(m['direction'],'NEUTRAL')
            self.assertIsNone(profiles.entry_block_reason(profiles.POLICIES['early100'],early))
            for changed in (
                {'earlyImpulse':{**m['earlyImpulse'],'available':False}},
                {'earlyImpulse':{**m['earlyImpulse'],'extensionRisk':True}},
                {'earlyImpulse':{**m['earlyImpulse'],'barAt':NOW-3600001}},
                {'earlyPaperPlan':None},
                {'priceFresh':False},
                {'ruleVersion':'legacy-rule'},
            ):
                blocked=profiles.early_paper_market({**m,**changed},NOW)
                self.assertEqual(blocked['direction'],'NEUTRAL')
                self.assertIsNone(blocked['plan'])
                self.assertIsNotNone(profiles.entry_block_reason(profiles.POLICIES['early100'],blocked))

    def test_early_plan_rejection_preserves_specific_reason(self):
        m=market()
        m.update(ruleVersion='intraday-trend-follow-v7',
                 earlyImpulse=dict(version='early-impulse-v1',direction='SHORT',
                     available=True,comparisonOnly=True,affectsApproval=False,
                     extensionRisk=False,barAt=NOW-300000),
                 earlyPaperPlan=None,earlyPaperPlanReason='Unterstützung vor dem Ziel: Mindest-CRV nicht erfüllt')
        result=profiles.early_paper_market(m,NOW)
        self.assertIn('Unterstützung vor dem Ziel',result['earlyPaperBlockReason'])
        self.assertEqual(result['direction'],'NEUTRAL')
        self.assertIsNone(result['plan'])

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'Postgres integration requires CI database')
    def test_new_early_account_virtual_entry_independent_from_other_accounts(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            with patch('paper_portfolios.time.time',return_value=NOW/1000):
                sim.init(conn)
            m=market(50,'NEUTRAL')
            m.update(ruleVersion='intraday-trend-follow-v7',
                     earlyImpulse=dict(version='early-impulse-v1',direction='SHORT',
                         available=True,comparisonOnly=True,affectsApproval=False,
                         extensionRisk=False,barAt=NOW-300000),
                     earlyPaperPlan=dict(kind='candidate',direction='SHORT',entry=4000.,
                         stop=4020.,target=3960.,unit='USD/oz'))
            em=profiles.early_paper_market(m,NOW)
            chosen={'choices':[{'isin':ISIN,'direction':'SHORT','approval':'Bob-Pflichtprüfung bestanden'}]}
            # A product missing KO verification must never be bought, even
            # in a fictional research account.
            status=profiles.run_all(conn,{},m,{'choices':[]},{ISIN:quote()},NOW,{},
                                    early_market=em,early_selection=chosen)
            ns=profiles.names('early100')
            self.assertIsNone(conn.execute('SELECT payload FROM '+ns['bob_paper_cases']).fetchone())
            blocked=conn.execute('SELECT payload FROM '+ns['bob_paper_control']).fetchone()[0]
            self.assertIn('KO-Schutz',blocked['reason'])
            safe={'choices':[{'isin':ISIN,'direction':'SHORT',
                              'approval':'Bob-Pflichtprüfung bestanden',
                              'koGuardRequired':True,'scope':'XAU/USD'}]}
            with patch('paper_ko_guard.entry_reason',return_value=(None,{'ok':True})) as verify:
                status=profiles.run_all(conn,{},m,{'choices':[]},{ISIN:quote()},NOW,{},
                                        early_market=em,early_selection=safe)
                self.assertTrue(verify.called)
            self.assertEqual(status['early100'],'checked')
            case=conn.execute('SELECT payload FROM '+ns['bob_paper_cases']).fetchone()
            self.assertIsNotNone(case)
            self.assertEqual(case[0]['entryHypothesis'],'early-impulse-paper-v1')
            self.assertEqual(case[0]['engine']['trade']['dir'],'SHORT')
            self.assertEqual(case[0]['quantity'],6)
            for name in ('conservative','balanced','offensive','trend800'):
                self.assertIsNone(conn.execute('SELECT id FROM '+profiles.names(name)['bob_paper_cases']).fetchone())
            self.assertFalse(hasattr(profiles, 'place_order'))
            conn.rollback()

    def test_tables_are_namespaced_except_shared_product_quotes(self):
        sql=[]
        class Conn:
            def execute(self, text, params=()):
                sql.append(text)
                return self
        conn=Conn()
        for profile in profiles.POLICIES:
            profiles.Ledger(conn,profile).execute(
                'SELECT payload FROM bob_paper_cases WHERE closed_at IS NULL')
        self.assertEqual(len(set(sql)),7)
        self.assertNotIn('bob_paper_cases WHERE',sql[0])
        profiles.Ledger(conn,'balanced').execute(
            'SELECT payload FROM bob_paper_products')
        self.assertEqual(sql[-1],'SELECT payload FROM bob_paper_products')
        with self.assertRaises(ValueError):
            profiles.names('public; DROP TABLE users')

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                         'Postgres integration requires CI database')
    def test_isolated_balances_and_forward_trades_in_postgres(self):
        import psycopg
        conn=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'])
        try:
            with patch('paper_portfolios.time.time',return_value=NOW/1000):sim.init(conn)
            for profile in profiles.POLICIES:
                control=conn.execute('SELECT payload FROM '+
                   profiles.names(profile)['bob_paper_control']+' WHERE id=1').fetchone()[0]
                expected_capital=profiles.POLICIES[profile].get('initial_capital_eur',100.)
                self.assertEqual(control['cash'],expected_capital)
                self.assertEqual(control['equity'],expected_capital)
                self.assertEqual(control['startAt'],NOW if profile=='early100' or profiles.POLICIES[profile].get('campaign') else profiles.START)
            found=profiles.run_all(conn,{},market(),
                {'choices':[{'isin':ISIN,'approval':'Bob-Pflichtprüfung bestanden'}]},
                {ISIN:quote()},NOW,settings={})
            self.assertEqual(found,{name:'checked' for name in profiles.POLICIES})
            expected={'conservative':3,'balanced':6,'offensive':9,'trend800':51}
            for profile in ('conservative','balanced','offensive','trend800'):
                ns=profiles.names(profile)
                row=conn.execute('SELECT payload FROM '+ns['bob_paper_cases']).fetchone()
                self.assertIsNotNone(row,profile)
                self.assertEqual(row[0]['quantity'],expected[profile])
                self.assertEqual(row[0]['profile'],profile)
                self.assertNotIn('DEGIRO',row[0]['capitalMode'])
                control=conn.execute('SELECT payload FROM '+ns['bob_paper_control']).fetchone()[0]
                self.assertAlmostEqual(control['cash'],(800 if profile=='trend800' else 100)-expected[profile]*10.1)
                self.assertFalse(bool(row[0].get('trendFollow')))
                if profile == 'trend800':
                    self.assertEqual(row[0]['exitPolicy'], 'bob-stop-reentry-v1')
            # A normal market direction never authorizes the experimental account.
            experimental=profiles.names('early100')
            self.assertIsNone(conn.execute('SELECT payload FROM '+experimental['bob_paper_cases']).fetchone())
            # The older single-account ledger receives no new entry.
            count=conn.execute('SELECT count(*) FROM bob_paper_cases').fetchone()[0]
            self.assertEqual(count,0)
            view=profiles.report(conn, '2026-10-12')
            self.assertEqual(view['mode'],'seven-independent-paper-accounts')
            self.assertEqual(view['simulatedCapitalEur'],3200)
            self.assertFalse(view['realOrders'])
            self.assertEqual(len(view['accounts']),7)
            self.assertEqual({x['profile'] for x in view['accounts']},set(profiles.POLICIES))
        finally:
            conn.rollback()
            conn.close()


if __name__ == '__main__':
    unittest.main()
