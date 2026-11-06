import copy
import json
import os
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import intraday_timing_study as s

NOW = int(datetime(2026,11,6,10,30,tzinfo=timezone.utc).timestamp()*1000)


def sample(now=NOW, price=4002., trend='LONG'):
    end=int(now//60000)*60000
    rows=[dict(openTime=end-(120-i)*60000,open=4000.,high=4001.,low=3999.,close=4000.,
               instrument='XAU/USD',source='test',isOpen=False) for i in range(120)]
    for i in range(115,120):
        rows[i].update(open=4001.5,high=4002.1,low=4001.4,close=4002.)
    b=dict(spots=dict(xaus=price,is_genuine_xauusd_spot=True,xaus_is_spot=True,
                     spot_price_as_of=datetime.fromtimestamp(now/1000,timezone.utc).isoformat()),
           history=dict(bars_by_tf={'1m':rows,'1h':[dict(instrument='XAU/USD',isOpen=False,openTime=now//3600000*3600000-3600000)]}))
    m=dict(direction='NEUTRAL',dataAt=now,ruleVersion='test',
           trendContext=dict(available=True,direction=trend),decisionReason='hour neutral')
    return b,m


def forced(rows,minutes,now,pullback=False):
    return dict(available=True,direction='LONG',barAt=NOW-300000,closedAt=NOW,
                ema='LONG',macd='LONG',atr=2.,estimated=any(b.get('estimated') for b in rows),level=4001.)


class Inputs(unittest.TestCase):
    def test_common_lookback_and_actual_aggregation(self):
        b,m=sample();before=copy.deepcopy(b)
        rows,error=s.minute_history(b,NOW)
        self.assertIsNone(error);self.assertEqual(len(rows),120)
        for n in (3,5,7):
            bars=s.aggregate(rows,n,NOW)
            self.assertTrue(bars)
            self.assertTrue(all(b['closeTime']<=NOW and b['openTime']%(n*60000)==0 for b in bars))
            self.assertTrue(s.frame_signal(rows,n,NOW)['available'])
        self.assertEqual(b,before)
        signal=s.frame_signal(rows,5,NOW)
        self.assertEqual(signal['direction'],'LONG')
        self.assertEqual(signal['ema'],'LONG')
        self.assertEqual(signal['macd'],'LONG')

    def test_short_pipeline_is_symmetric(self):
        b,m=sample(price=3998.,trend='SHORT')
        for r in b['history']['bars_by_tf']['1m']:
            r.update(open=8000-r['open'],close=8000-r['close'],high=8000-r['low'],low=8000-r['high'])
        state,closed=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        p=state['arms']['original:base5:30']['position']
        self.assertEqual(p['direction'],'SHORT')
        self.assertGreater(p['stop'],p['entryPrice']);self.assertLess(p['target'],p['entryPrice'])

    def test_no_future_leakage_or_input_mutation(self):
        b,m=sample();rows,_=s.minute_history(b,NOW);first=s.frame_signal(rows,5,NOW)
        b['history']['bars_by_tf']['1m'].append(dict(openTime=NOW,open=9999.,close=9999.,high=10000.,low=9998.,instrument='XAU/USD',isOpen=False))
        later,_=s.minute_history(b,NOW)
        self.assertEqual(s.frame_signal(later,5,NOW),first)

    def test_only_two_missing_minutes_are_causally_carried(self):
        b,m=sample();raw=b['history']['bars_by_tf']['1m'];expected=raw[113]['close']
        del raw[114:116]
        self.assertFalse(s.minute_history(b,NOW)[0])
        rows,error=s.minute_history(b,NOW,True)
        self.assertIsNone(error);self.assertEqual(sum(bool(r.get('estimated')) for r in rows),2)
        self.assertEqual(rows[114]['close'],expected)
        del raw[112]
        self.assertFalse(s.minute_history(b,NOW,True)[0])

    def test_malformed_duplicate_mixed_open_never_repaired(self):
        for fault in ('duplicate','instrument','high','open','estimated','source'):
            b,m=sample();rows=b['history']['bars_by_tf']['1m']
            if fault=='duplicate':rows.append(copy.deepcopy(rows[-1]))
            elif fault=='instrument':rows[-1]['instrument']='GC=F'
            elif fault=='high':rows[-1]['high']=1
            elif fault=='open':rows[-1]['providerIsOpen']=True
            elif fault=='estimated':rows[-1]['estimated']=True
            else:rows[-1]['source']='other'
            self.assertFalse(s.minute_history(b,NOW,True)[0],fault)

    def test_neutral_missing_opposed_and_single_gate_ablations(self):
        sig=forced([],5,NOW)
        self.assertFalse(s.gate(sig,dict(available=True,direction='NEUTRAL'),s.VARIANTS['base5'])[0])
        self.assertTrue(s.gate(sig,dict(available=True,direction='NEUTRAL'),s.VARIANTS['neutral5'])[0])
        for trend in ({},dict(available=False,direction='NEUTRAL'),dict(available=True,direction='SHORT')):
            self.assertFalse(s.gate(sig,trend,s.VARIANTS['neutral5'])[0])
        trend=dict(available=True,direction='LONG')
        self.assertTrue(s.gate({**sig,'ema':'SHORT'},trend,s.VARIANTS['noema5'])[0])
        self.assertFalse(s.gate({**sig,'ema':'SHORT','macd':'SHORT'},trend,s.VARIANTS['noema5'])[0])
        self.assertTrue(s.gate({**sig,'macd':'SHORT'},trend,s.VARIANTS['nomacd5'])[0])

    def test_closed_bar_pullback_requires_retest_and_recovery(self):
        b,m=sample();raw=b['history']['bars_by_tf']['1m']
        for i in range(105,110):raw[i].update(open=4001.5,close=4002.,high=4002.1,low=4001.4)
        for i in range(110,115):raw[i].update(open=4001.,close=4000.8,high=4001.2,low=4000.5)
        rows,_=s.minute_history(b,NOW)
        self.assertEqual(s.frame_signal(rows,5,NOW,True)['direction'],'LONG')
        for i in range(110,115):raw[i].update(open=4001.5,close=4001.5,high=4001.8,low=4001.3)
        rows,_=s.minute_history(b,NOW)
        self.assertIsNone(s.frame_signal(rows,5,NOW,True)['direction'])


class StateMachine(unittest.TestCase):
    def run_tick(self,state,now=NOW,price=4002.,trend='LONG'):
        b,m=sample(now,price,trend)
        with patch.object(s,'frame_signal',side_effect=forced):
            return s.advance(state,b,m,{}, {},now)

    def test_real_signal_pipeline_and_48_bounded_arms(self):
        b,m=sample();state=s.seed(NOW);before=copy.deepcopy((b,m,state))
        result,closed=s.advance(state,b,m,{}, {},NOW)
        self.assertEqual((b,m,state),before)
        self.assertEqual(len(result['arms']),48)
        self.assertEqual(result['arms']['original:base5:30']['started'],1)
        self.assertEqual(result['arms']['original:pullback5:30']['started'],0)
        self.assertFalse(closed)
        json.dumps(result,allow_nan=False)

    def test_duplicates_gap_and_no_same_cycle_reentry(self):
        state,_=self.run_tick(s.seed(NOW))
        again,done=self.run_tick(state)
        self.assertEqual(again,state);self.assertFalse(done)
        again,done=self.run_tick(state,NOW+120000)
        self.assertEqual(len(done),48)
        self.assertTrue(all(p['status']=='inconclusive' and p['netPct'] is None for p in done))
        self.assertTrue(all(a['started']==1 and not a['position'] for a in again['arms'].values()))

    def test_time_stop_and_horizons_use_observed_price(self):
        state,_=self.run_tick(s.seed(NOW));done=[]
        for delta in range(30000,600001,30000):
            state,closed=self.run_tick(state,NOW+delta);done+=closed
        self.assertEqual({p['arm'] for p in done},{'original:timestop5:30','modeled:timestop5:30'})
        self.assertTrue(all(p['exitReason']=='no-progress' for p in done))
        self.assertTrue(all(abs(p['netPct']+.16)<1e-8 for p in done))
        self.assertIsNotNone(state['arms']['original:base5:30']['position'])
        self.assertIsNotNone(state['arms']['original:timestop5:180']['position'])
        for delta in range(630000,1800001,30000):
            state,closed=self.run_tick(state,NOW+delta);done+=closed
        base=next(p for p in done if p['arm']=='original:base5:30')
        self.assertEqual(base['exitReason'],'horizon')
        self.assertIsNotNone(state['arms']['original:base5:300']['position'])

    def test_stop_records_adverse_and_false_start_not_target_fill(self):
        state,_=self.run_tick(s.seed(NOW));state,done=self.run_tick(state,NOW+30000,3997.)
        p=next(p for p in done if p['arm']=='original:base5:30')
        self.assertEqual(p['exitPrice'],3997.)
        self.assertEqual(p['exitReason'],'stop')
        self.assertGreater(p['maxAdversePct'],0)
        self.assertEqual(state['arms']['original:base5:30']['falseStarts'],1)
        state,done=self.run_tick(state,NOW+60000,4002.)
        self.assertFalse(done);self.assertEqual(state['arms']['original:base5:30']['started'],1)

    def test_missing_hour_blocks_even_neutral_variant(self):
        b,m=sample(trend='NEUTRAL');b['history']['bars_by_tf']['1h']=[]
        with patch.object(s,'frame_signal',side_effect=forced):state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertTrue(all(a['started']==0 for a in state['arms'].values()))
        self.assertEqual(state['arms']['original:neutral5:30']['reason'],'hour-context-missing')

    def test_estimated_signals_separate_and_late_entry_rejected(self):
        b,m=sample();del b['history']['bars_by_tf']['1m'][110]
        with patch.object(s,'frame_signal',side_effect=forced):state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
        self.assertEqual(state['arms']['original:base5:30']['started'],0)
        self.assertTrue(state['arms']['modeled:base5:30']['position']['estimatedUsed'])
        state,done=self.run_tick(state,NOW+30000,3997.)
        a=state['arms']['modeled:base5:30'];self.assertEqual(a['estimatedClosed'],1);self.assertEqual(a['originalClosed'],0)
        late,_=self.run_tick(s.seed(NOW),price=4010.)
        self.assertTrue(all(a['started']==0 for a in late['arms'].values()))
        self.assertEqual(late['arms']['original:base5:30']['reason'],'entry-too-late')

    def test_expiry_drains_no_new_positions_and_caps(self):
        state,_=self.run_tick(s.seed(NOW));state['deadlineAt']=NOW+1
        state,done=self.run_tick(state,NOW+30000,3997.)
        self.assertEqual(state['status'],'completed-review-required')
        state,done=self.run_tick(state,NOW+60000)
        self.assertTrue(all(a['started']==1 for a in state['arms'].values()))

    def test_future_and_stale_prices_never_create_entries(self):
        for shift in (1,-61000):
            b,m=sample();b['spots']['spot_price_as_of']=datetime.fromtimestamp((NOW+shift)/1000,timezone.utc).isoformat()
            with patch.object(s,'frame_signal',side_effect=forced):state,_=s.advance(s.seed(NOW),b,m,{}, {},NOW)
            self.assertTrue(all(a['started']==0 for a in state['arms'].values()))

    def test_latency_observed_times_and_expiry(self):
        state=s.seed(NOW);b,m=sample()
        m['earlyWarning']=dict(direction='LONG',signalBarAt=NOW-300000,state='active',expiresAt=NOW+600000)
        s.latency(state,m,{}, {},NOW)
        self.assertIsNone(state['latency']['confirmationObservedAt'])
        m['direction']='LONG';s.latency(state,m,{}, {},NOW+30000)
        self.assertEqual(state['latency']['confirmationDelayMs'],30000)
        self.assertIsNone(state['latency']['pushSentAt'])
        state['latency']['confirmationObservedAt']=None
        s.latency(state,m,{}, {},NOW+16*60000)
        self.assertIsNone(state['latency']['confirmationObservedAt'])
        self.assertEqual(state['latency']['status'],'expired')

    def test_withdrawn_warning_cannot_correlate_a_later_confirmation(self):
        state=s.seed(NOW);b,m=sample()
        m['earlyWarning']=dict(direction='LONG',signalBarAt=NOW-300000,state='active',expiresAt=NOW+600000)
        s.latency(state,m,{}, {},NOW)
        m['earlyWarning']['state']='withdrawn';m['direction']='LONG'
        s.latency(state,m,{}, {},NOW+30000)
        self.assertEqual(state['latency']['status'],'withdrawn')
        self.assertIsNone(state['latency']['confirmationObservedAt'])

    def test_push_requires_matching_original_warning(self):
        a=dict(signalBarAt=NOW,direction='LONG')
        good=dict(signalBarAt=NOW,direction='LONG',test=False,synthetic=False,eventKinds=['early-warning'],outcome='provider-accepted',providerStartedAt=NOW+5000)
        with patch('push_delivery_history.report',return_value=dict(records=[{**good,'test':True},{**good,'direction':'SHORT'},good],nextOffset=None)):
            result=s.push_evidence(None,a)
        self.assertEqual(result['matchedPushAttempts'],1)
        self.assertEqual(result['pushSentAt'],NOW+5000)
        self.assertIsNone(result['pushBrowserReceiptAt'])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'test PostgreSQL unavailable')
class Database(unittest.TestCase):
    def test_durable_tick_report_and_retry(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            # All objects/rows isolated by rollback, never touches an existing study.
            with conn.transaction(force_rollback=True):
                conn.execute('CREATE SCHEMA timing_test')
                conn.execute('SET LOCAL search_path TO timing_test')
                s.init(conn)
                b,m=sample()
                s.tick(conn,b,m,{}, {},NOW);s.tick(conn,b,m,{}, {},NOW)
                report=s.report(conn)
                self.assertEqual(len(report['variants']),48)
                b,m=sample(NOW+30000,3990.)
                s.tick(conn,b,m,{}, {},NOW+30000)
                before=conn.execute('SELECT count(*) FROM bob_intraday_timing_cases').fetchone()[0]
                self.assertGreater(before,0)
                s.tick(conn,b,m,{}, {},NOW+30000)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_intraday_timing_cases').fetchone()[0],before)
                self.assertFalse(s.report(conn)['strategyWinnerConfirmed'])
