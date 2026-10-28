import copy
import unittest
from test_paper_ko_guard import NOW, ISIN, quote, choice
import risk_paper as r


def signal(at=NOW, stage='BESTÄTIGT', direction='LONG'):
    return dict(ready=True,at=at,barAt=at-60000,spot=4000.,atr=2.,stage=stage,direction=direction)


def result(at=NOW, action=None):
    return dict(signal=signal(at),choices=[choice()],watches={str(d):{'action':action or 'BEOBACHTEN'} for d in r.DELAYS})


class RiskPaperTests(unittest.TestCase):
    def step(self,s,at=NOW,action=None,q=None):
        return r.advance(s,result(at,action),{ISIN:q or quote(at)},at)

    def test_delays_require_new_quotes_and_do_not_overdraw(self):
        s,_=self.step(r.seed(NOW))
        self.assertIsNotNone(s['accounts']['0']['position'])
        self.assertIsNone(s['accounts']['30']['position'])
        s,_=self.step(s,NOW+30000,q=quote(NOW))
        self.assertIsNone(s['accounts']['30']['position'])
        s,_=self.step(s,NOW+30000)
        self.assertIsNotNone(s['accounts']['30']['position'])
        self.assertIsNone(s['accounts']['60']['position'])
        s,_=self.step(s,NOW+60000)
        for a in s['accounts'].values():
            self.assertLessEqual(a['position']['debit'],1000)
            self.assertGreaterEqual(a['cash'],1000)

    def test_bid_ask_costs_and_exit_delays(self):
        s,_=self.step(r.seed(NOW));s,_=self.step(s,NOW+60000)
        s,c=self.step(s,NOW+90000,'AUSSTIEG PRÜFEN',quote(NOW+90000,bid=11.))
        self.assertEqual(len(c),1)
        units=c[0]['units']
        self.assertAlmostEqual(c[0]['modelNet'],units*(11.-10.1)-10)
        self.assertIsNotNone(s['accounts']['30']['position'])
        s,c=self.step(s,NOW+120000,'BEOBACHTEN',quote(NOW+120000,bid=9.))
        self.assertEqual(len(c),1)
        self.assertEqual(c[0]['delaySeconds'],30)
        self.assertEqual(c[0]['exitQuote']['bid'],9.)

    def test_stale_terminal_and_fx_cannot_fake_settlement(self):
        s,_=self.step(r.seed(NOW))
        s,_=self.step(s,NOW+30000,'AUSSTIEG PRÜFEN',quote(NOW))
        self.assertIsNotNone(s['accounts']['0']['position'])
        s,_=self.step(s,NOW+60000,q=quote(NOW+60000,status=2))
        self.assertIsNone(s['accounts']['0']['equity'])
        s,c=self.step(s,NOW+90000,q=quote(NOW+90000))
        self.assertFalse(c)
        fx=quote();fx['paperFxConversion']={'rate':1.1}
        self.assertIsNone(r.usable(fx,ISIN,NOW,NOW))

    def test_no_entry_on_warning_or_bad_terms_and_immutable_input(self):
        old=r.seed(NOW);before=copy.deepcopy(old)
        x=result();x['signal']['stage']='VORWARNUNG'
        s,_=r.advance(old,x,{ISIN:quote()},NOW)
        self.assertEqual(old,before)
        self.assertTrue(all(a['position'] is None for a in s['accounts'].values()))
        q=quote();q['conditions']['ko']['dateText']='11.10.2026'
        s,_=self.step(old,q=q)
        self.assertTrue(all(a['position'] is None for a in s['accounts'].values()))

    def test_gap_is_counted_and_never_ready_after_just_one_trade(self):
        s,_=self.step(r.seed(NOW))
        s,c=self.step(s,NOW+120000,'AUSSTIEG PRÜFEN',quote(NOW+120000,bid=9))
        self.assertTrue(c[0]['dataGap'])
        a=s['accounts']['0']
        self.assertEqual(a['incomplete'],1)
        self.assertFalse(a['reviewReady'])
        self.assertGreater(a['maxDrawdown'],0)

    def test_signal_withdrawal_cancels_pending_and_closed_episode_not_reentered(self):
        s,_=self.step(r.seed(NOW))
        x=result(NOW+30000);x['signal']['direction']='ABWARTEN'
        s,_=r.advance(s,x,{ISIN:quote(NOW+30000)},NOW+30000)
        self.assertIsNone(s['accounts']['30']['pending'])
        s,c=self.step(s,NOW+60000,'AUSSTIEG PRÜFEN')
        s,_=self.step(s,NOW+90000)
        self.assertIsNone(s['accounts']['0']['position'])

if __name__=='__main__':unittest.main()

# CI provides an isolated PostgreSQL database. Temporary tables never touch live accounts.
import os
from unittest.mock import patch, Mock
@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'isolated PostgreSQL not configured')
class RiskPaperDatabaseTests(unittest.TestCase):
    def test_restart_idempotent_initialization_and_durable_settlement(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_risk_paper (id INTEGER PRIMARY KEY, payload JSONB NOT NULL) ON COMMIT DROP')
            conn.execute('CREATE TEMP TABLE bob_risk_paper_cases (id TEXT PRIMARY KEY, payload JSONB NOT NULL) ON COMMIT DROP')
            with patch('risk_paper.time.time',return_value=NOW/1000):r.init(conn)
            with patch('risk_paper.evaluator_runtime.run',return_value=Mock(stdout=__import__('json').dumps(result()))), patch('risk_paper.time.time',return_value=NOW/1000), patch('background_push.degiro_entry_allowed',return_value=True):
                r.tick(conn,{}, {'products':[]},{ISIN:quote()},NOW)
            self.assertIn(ISIN,r.active_isins(conn))
            first=r.report(conn)
            r.init(conn)
            self.assertEqual(r.report(conn),first,'deploy must not reset money or positions')
            at=NOW+30000
            with patch('risk_paper.evaluator_runtime.run',return_value=Mock(stdout=__import__('json').dumps(result(at,'AUSSTIEG PRÜFEN')))), patch('risk_paper.time.time',return_value=at/1000), patch('background_push.degiro_entry_allowed',return_value=True):
                r.tick(conn,{}, {'products':[]},{ISIN:quote(at,bid=11)},at)
                r.tick(conn,{}, {'products':[]},{ISIN:quote(at,bid=11)},at)
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_risk_paper_cases').fetchone()[0],1)
            self.assertEqual(r.report(conn)['accounts']['0']['closed'],1)
