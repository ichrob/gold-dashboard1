"""Regression tests for three isolated Monday paper accounts (no real orders)."""
import json
import os
import unittest
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
    def test_three_100_and_one_800_eur_accounts(self):
        self.assertEqual(list(profiles.POLICIES),
                         ['conservative','balanced','offensive','trend800'])
        self.assertEqual(len(set(profiles.names(p)['bob_paper_cases']
                                 for p in profiles.POLICIES)),4)
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
        self.assertEqual(len(set(sql)),3)
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
            sim.init(conn)
            for profile in profiles.POLICIES:
                control=conn.execute('SELECT payload FROM '+
                   profiles.names(profile)['bob_paper_control']+' WHERE id=1').fetchone()[0]
                expected_capital=800. if profile=='trend800' else 100.
                self.assertEqual(control['cash'],expected_capital)
                self.assertEqual(control['equity'],expected_capital)
                self.assertEqual(control['startAt'],profiles.START)
            found=profiles.run_all(conn,{},market(),
                {'choices':[{'isin':ISIN,'approval':'Bob-Pflichtprüfung bestanden'}]},
                {ISIN:quote()},NOW,settings={})
            self.assertEqual(found,{name:'checked' for name in profiles.POLICIES})
            expected={'conservative':3,'balanced':6,'offensive':9,'trend800':51}
            for profile in profiles.POLICIES:
                ns=profiles.names(profile)
                row=conn.execute('SELECT payload FROM '+ns['bob_paper_cases']).fetchone()
                self.assertIsNotNone(row,profile)
                self.assertEqual(row[0]['quantity'],expected[profile])
                self.assertEqual(row[0]['profile'],profile)
                self.assertNotIn('DEGIRO',row[0]['capitalMode'])
                control=conn.execute('SELECT payload FROM '+ns['bob_paper_control']).fetchone()[0]
                self.assertAlmostEqual(control['cash'],(800 if profile=='trend800' else 100)-expected[profile]*10.1)
                self.assertEqual(bool(row[0].get('trendFollow')),profile=='trend800')
            # The older single-account ledger receives no new entry.
            count=conn.execute('SELECT count(*) FROM bob_paper_cases').fetchone()[0]
            self.assertEqual(count,0)
            view=profiles.report(conn, '2026-10-12')
            self.assertEqual(view['mode'],'four-independent-paper-accounts')
            self.assertEqual(view['simulatedCapitalEur'],1100)
            self.assertFalse(view['realOrders'])
            self.assertEqual(len(view['accounts']),4)
            self.assertEqual({x['profile'] for x in view['accounts']},set(profiles.POLICIES))
        finally:
            conn.rollback()
            conn.close()


if __name__ == '__main__':
    unittest.main()
