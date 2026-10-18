"""Monday 12 Oct 2026: forward-paper market feed and safety regression."""
import copy
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import background_push
import paper_simulation as sim


def millis(day, hour, minute=0):
    return int(datetime(2026, 10, day, hour, minute,
                        tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)


class PaperMondayTests(unittest.TestCase):
    def test_monday_trading_window_is_not_a_market_data_guarantee(self):
        self.assertEqual(background_push.degiro_session(millis(12, 7, 59)), 'preparation')
        self.assertEqual(background_push.degiro_session(millis(12, 8)), 'trading')
        self.assertEqual(background_push.degiro_session(millis(12, 21, 59)), 'trading')
        self.assertEqual(background_push.degiro_session(millis(12, 22)), 'night')
        self.assertEqual(background_push.degiro_session(millis(11, 12)), 'weekend')

    def test_bob_scans_without_push_or_old_four_day_study(self):
        source=Path('server.py').read_text(encoding='utf-8')
        self.assertIn('active or intraday_comparison.active() or background_push.degiro_session() == "trading"',source)
        self.assertIn('paper_simulation.enqueue(bundle,db)',Path('push_server.py').read_text(encoding='utf-8'))

    def test_ledger_is_durable_and_uses_existing_authenticated_audit_path(self):
        audit=Path('decision_audit.py').read_text(encoding='utf-8')
        self.assertIn('paper_simulation.init(conn)', audit)
        self.assertIn("paper_simulation.report(conn,payload.get('day'))",audit)
        self.assertIn('paper_simulation.sync(conn,payload)',audit)
        ui=Path('Bob.html').read_text(encoding='utf-8')
        self.assertIn("move(byId('paperSimulationPanel'),'learning')",ui)
        self.assertIn('id="bob-portfolio-comparison"',
                      Path('vollautomatisch_panel.py').read_text(encoding='utf-8'))

    def test_missing_and_stale_product_quote_block_eur_paper_entry(self):
        now=millis(12, 9)
        isin='DE000PJ9NCK0'
        def run(quote, choice=None, control=None):
            control=control or {'startAt':sim.START,'enabled':True,
                                'initialCapital':100.,'cash':100.,'equity':100.}
            stored=[]
            def execute(sql,args=()):
                stored.append((sql,args))
                cursor=Mock()
                if sql.startswith('SELECT payload FROM bob_paper_control'):
                    cursor.fetchone.return_value=(copy.deepcopy(control),)
                elif sql.startswith('SELECT id,payload FROM bob_paper_cases'):
                    cursor.fetchone.return_value=None
                elif sql.startswith('SELECT payload FROM bob_paper_days'):
                    cursor.fetchone.return_value=None
                else:
                    cursor.fetchone.return_value=None
                return cursor
            conn=Mock();conn.execute.side_effect=execute
            market=dict(plan=dict(kind='candidate',direction='LONG',entry=4000.,
                stop=3980.,target=4040.,unit='USD/oz'),ready=True,priceFresh=True,
                price=4000.,dataAt=now,analysisBarAt=now,ruleVersion='test-v1',
                direction='LONG',session={'entryAllowed':True})
            c=choice or {'isin':isin}
            sim.run_once(conn,{},market,{'choices':[c]},{isin:quote} if quote else {},now)
            self.assertFalse(any('INSERT INTO bob_paper_cases' in sql for sql,_ in stored))
            updates=[json.loads(args[0]) for sql,args in stored if sql.startswith('UPDATE bob_paper_control')]
            return updates[-1]['reason']
        self.assertIn('Geld-/Briefkurs',run(None))
        stale={'isin':isin,'found':True,'marketOpen':True,'currency':'EUR',
               'bid':8.,'ask':8.1,'source':'issuer', 'bidAt':now-120000,'askAt':now-120000}
        self.assertIn('Geld-/Briefkurs',run(stale))
        fresh={**stale,'bidAt':now,'askAt':now}
        self.assertIn('Unverbindlicher',run(fresh,{'isin':isin,'indicative':True}))
        self.assertIn('Tagesverlustgrenze',run(fresh, control={
            'startAt':sim.START,'enabled':True,'initialCapital':100.,
            'cash':96.,'equity':96.,'ledgerDay':'2026-10-12',
            'dayOpeningEquity':100.,'realizedProfit':-4.}))


if __name__ == '__main__':
    unittest.main()
