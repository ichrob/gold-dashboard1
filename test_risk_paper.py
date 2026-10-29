import copy
import unittest
from test_paper_ko_guard import NOW, ISIN, quote, choice
import risk_paper as r


def signal(at=NOW, stage='BESTÄTIGT', direction='LONG'):
    return dict(ready=True,at=at,barAt=at-60000,spot=4000.,atr=2.,stage=stage,direction=direction)


def result(at=NOW, action=None):
    return dict(signal=signal(at),choices=[choice()],watches={str(d):{'action':action or 'BEOBACHTEN'} for d in r.DELAYS})


class RiskPaperTests(unittest.TestCase):
    def test_expired_unfilled_attempt_retries_with_new_delay_and_quote(self):
        s,_=r.advance(r.seed(NOW),result(),{},NOW)
        for a in s['accounts'].values():
            self.assertIsNone(a['lastSignal'])
        s,_=r.advance(s,result(NOW+151000),{},NOW+151000)
        for a in s['accounts'].values():
            self.assertIsNone(a['pending'])
            self.assertEqual(a['cash'],2000)
        at=NOW+152000
        s,_=self.step(s,at,q=quote(NOW))
        for d in r.DELAYS:
            a=s['accounts'][str(d)]
            self.assertIsNone(a['position'])
            self.assertEqual(a['pending']['due'],at+d*1000)
        for offset in (0,30000,60000):
            s,_=self.step(s,at+offset)
        for a in s['accounts'].values():
            self.assertIsNotNone(a['position'])
            self.assertEqual(a['lastSignal'],'LONG')

    def test_legacy_unfilled_lock_recovers_but_closed_episode_stays_locked(self):
        old=r.seed(NOW)
        for a in old['accounts'].values():a['lastSignal']='LONG'
        old['accounts']['60']['closed']=1
        s,_=self.step(old)
        self.assertIsNotNone(s['accounts']['0']['position'])
        self.assertIsNotNone(s['accounts']['30']['pending'])
        self.assertIsNone(s['accounts']['60']['pending'])
        self.assertIsNone(s['accounts']['60']['position'])
        self.assertNotIn('entryAttemptPolicy',old)

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

    def test_warning_enters_but_bad_terms_still_block_and_input_is_immutable(self):
        old=r.seed(NOW);before=copy.deepcopy(old)
        x=result();x['signal']['stage']='VORWARNUNG'
        s,_=r.advance(old,x,{ISIN:quote()},NOW)
        self.assertEqual(old,before)
        self.assertIsNotNone(s['accounts']['0']['position'])
        self.assertEqual(s['accounts']['0']['position']['entrySignalStage'],'VORWARNUNG')
        self.assertEqual(s['accounts']['0']['position']['entryPolicy'],r.ENTRY_POLICY)
        q=quote();q['conditions']['ko']['dateText']='11.10.2026'
        s,_=self.step(old,q=q)
        self.assertTrue(all(a['position'] is None for a in s['accounts'].values()))

    def test_real_minute_engine_warning_enters_long_and_short(self):
        import json, subprocess
        for direction,spot in (('LONG',4000.2),('SHORT',3999.8)):
            bars=[dict(openTime=NOW-(21-i)*60000,instrument='XAU/USD',
                       open=4000.,high=4001.,low=3999.,close=4000.) for i in range(21)]
            bundle={'spots':{'is_genuine_xauusd_spot':True,'xaus':spot,
                            'spot_price_as_of':__import__('datetime').datetime.fromtimestamp(
                                NOW/1000,__import__('datetime').timezone.utc).isoformat()},
                    'history':{'bars_by_tf':{'1m':bars}}}
            actual=json.loads(subprocess.check_output(
                ['node','-e',"const fs=require('fs'),r=require('./risk_workspace.js');const x=JSON.parse(fs.readFileSync(0));process.stdout.write(JSON.stringify(r.analyze(x.bundle,x.now)))"],
                input=json.dumps({'bundle':bundle,'now':NOW}),text=True))
            self.assertEqual(actual['stage'],'VORWARNUNG')
            self.assertEqual(actual['direction'],direction)
            x={'signal':actual,'choices':[choice(direction)]}
            q=quote(side=direction,ko=3900. if direction=='LONG' else 4100.)
            s,_=r.advance(r.seed(NOW),x,{ISIN:q},NOW)
            self.assertEqual(s['accounts']['0']['position']['direction'],direction)
            self.assertEqual(s['accounts']['30']['pending']['signal']['stage'],'VORWARNUNG')

    def test_estimated_minute_engine_enters_with_same_admission_and_saves_evidence(self):
        import json, subprocess
        for direction,spot in (('LONG',4000.2),('SHORT',3999.8)):
            bars=[dict(openTime=NOW-(22-i)*60000,instrument='XAU/USD',
                       open=4000.,high=4001.,low=3999.,close=4000.) for i in range(22)]
            bars[-1]['close']=4000.8 if direction=='LONG' else 3999.2
            bundle={'spots':{'is_genuine_xauusd_spot':True,'xaus':spot,
                            'spot_price_as_of':__import__('datetime').datetime.fromtimestamp(
                                (NOW-21000)/1000,__import__('datetime').timezone.utc).isoformat()},
                    'history':{'bars_by_tf':{'1m':bars}}}
            actual=json.loads(subprocess.check_output(
                ['node','-e',"const fs=require('fs'),r=require('./risk_workspace.js');const x=JSON.parse(fs.readFileSync(0));process.stdout.write(JSON.stringify(r.analyzePaper(x.bundle,x.now)))"],
                input=json.dumps({'bundle':bundle,'now':NOW+30000}),text=True))
            self.assertEqual(actual['dataMode'],'estimate')
            self.assertEqual(actual['sourceAt'],NOW-21000)
            self.assertEqual(actual['stage'],'VORWARNUNG')
            self.assertEqual(actual['direction'],direction)
            x={'signal':actual,'choices':[choice(direction)]}
            q=quote(NOW+30000,side=direction,ko=3900. if direction=='LONG' else 4100.)
            s,_=r.advance(r.seed(NOW),x,{ISIN:q},NOW+30000)
            self.assertEqual(s['accounts']['0']['position']['direction'],direction)
            self.assertEqual(s['accounts']['0']['position']['entryDataMode'],'estimate')
            self.assertEqual(s['accounts']['0']['position']['entryMarketEvidence']['sourceAt'],NOW-21000)
            self.assertEqual(s['accounts']['30']['pending']['signal']['stage'],'VORWARNUNG')

    def test_warning_confirmation_keeps_frozen_signal_and_delay(self):
        x=result();x['signal']['stage']='VORWARNUNG'
        s,_=r.advance(r.seed(NOW),x,{ISIN:quote()},NOW)
        first=copy.deepcopy(s['accounts']['0']['position'])
        s,_=self.step(s,NOW+30000)
        self.assertEqual(s['accounts']['0']['position']['id'],first['id'])
        p=s['accounts']['30']['position']
        self.assertEqual(p['signalAt'],NOW)
        self.assertEqual(p['entrySignalStage'],'VORWARNUNG')
        s,_=self.step(s,NOW+60000,'AUSSTIEG PRÜFEN')
        s,_=self.step(s,NOW+90000)
        self.assertIsNone(s['accounts']['0']['position'])

    def test_warning_withdrawal_stale_and_session_cancel_pending(self):
        x=result();x['signal']['stage']='VORWARNUNG'
        original,_=r.advance(r.seed(NOW),x,{ISIN:quote()},NOW)
        for kind in ('neutral','stale','session'):
            later=result(NOW+30000)
            later['signal']['stage']='VORWARNUNG'
            if kind=='neutral':later['signal']['direction']='ABWARTEN'
            if kind=='stale':later['signal']['at']=NOW-60001
            s,_=r.advance(original,later,{ISIN:quote(NOW+30000)},NOW+30000,
                          entry_allowed=kind!='session')
            self.assertIsNone(s['accounts']['30']['pending'])
            self.assertIsNone(s['accounts']['30']['position'])

    def test_warning_reversal_restarts_delay_for_new_side(self):
        x=result();x['signal']['stage']='VORWARNUNG'
        s,_=r.advance(r.seed(NOW),x,{ISIN:quote()},NOW)
        x={'signal':signal(NOW+30000,'VORWARNUNG','SHORT'),'choices':[choice('SHORT')]}
        s,_=r.advance(s,x,{ISIN:quote(NOW+30000,side='SHORT',ko=4100.)},NOW+30000)
        self.assertIsNone(s['accounts']['30']['position'])
        self.assertEqual(s['accounts']['30']['pending']['due'],NOW+60000)
        self.assertEqual(s['accounts']['30']['pending']['choice']['direction'],'SHORT')

    def test_rule_migration_preserves_money_history_and_legacy_pending(self):
        old,_=self.step(r.seed(NOW))
        old.pop('entryPolicy');old.pop('entryPolicyStartedAt')
        for a in old['accounts'].values():
            if a['pending']:a['pending'].pop('entryPolicy')
            if a['position']:a['position'].pop('entryPolicy')
            a['recent']=[{'legacy':'untouched'}]
        s,_=self.step(old,NOW+30000)
        self.assertEqual(s['entryPolicyStartedAt'],NOW+30000)
        self.assertEqual(s['accounts']['0']['cash'],old['accounts']['0']['cash'])
        self.assertNotIn('entryPolicy',s['accounts']['0']['position'])
        self.assertEqual(s['accounts']['30']['position']['entryPolicy'],r.LEGACY_ENTRY_POLICY)
        self.assertEqual(s['accounts']['0']['recent'],old['accounts']['0']['recent'])
        s2,_=self.step(s,NOW+60000)
        self.assertEqual(s2['entryPolicyStartedAt'],s['entryPolicyStartedAt'])

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



