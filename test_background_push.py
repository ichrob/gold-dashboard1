import copy
import json
import unittest
from unittest.mock import patch
import background_push as b
from test_push_monitor import PushMonitorTests
import push_server


class BackgroundRules(unittest.TestCase):
    def setUp(self):
        self.settings=b.config({'trade':{'active':True,'tradeId':'a','instrument':'XAU/USD','dir':'LONG','entry':100,'stop':90,'initialRisk':10,'target':150}})
        self.market={'ready':True,'priceFresh':True,'price':105,'dataAt':1800000000000,'direction':'LONG','mtf':'LONG','score':80,'atr':4}
    def kinds(self,events):
        return [e['data']['eventKind'] for e in events]
    def test_analysis_failure_preserves_source_time_and_reports_computation(self):
        market=b.failed_analysis_market({'spots':{'spot_price_as_of':'2026-01-01T10:00:00Z'}})
        self.assertIsNotNone(market['dataAt'])
        self.assertFalse(market['ready'])
        state, events=b.advance({},self.settings,market,True,False,now=0)
        self.assertEqual(events,[])
        state, _=b.advance(state,self.settings,market,True,False,now=30000)
        _, events=b.advance(state,self.settings,market,True,False,now=60000)
        self.assertIn('Hintergrundanalyse ist fehlgeschlagen',events[0]['body'])
        self.assertNotIn('Berechnung mit vorhandenen Werten läuft weiter',events[0]['body'])
        self.assertIsNone(b.failed_analysis_market({'spots':{'spot_price_as_of':'2026-01-01T10:00:00'}})['dataAt'])

    def test_zurich_weekend_hours_and_quote_gate(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo('Europe/Zurich')
        def stamp(day, hour, minute, second=0):
            return int(datetime(2026, 10, day, hour, minute, second, tzinfo=tz).timestamp() * 1000)
        close = stamp(9, 23, 0)
        self.assertIsNone(b.gold_weekend_close(stamp(9, 22, 59)))
        self.assertEqual(b.gold_weekend_close(stamp(9, 23, 0)), close)
        self.assertEqual(b.gold_weekend_close(stamp(10, 6, 0)), close)
        self.assertEqual(b.gold_weekend_close(stamp(11, 23, 59)), close)
        self.assertIsNone(b.gold_weekend_close(stamp(12, 0, 0)))
        self.assertTrue(b.weekend_quote_at_close(stamp(10, 6, 0), stamp(9, 23, 1, 14)))
        self.assertFalse(b.weekend_quote_at_close(stamp(10, 6, 0), stamp(9, 22, 0)))
        self.assertFalse(b.weekend_quote_at_close(stamp(9, 22, 59), stamp(9, 22, 59)))
        # The local trading times must survive Switzerland's DST change.
        self.assertEqual(datetime.fromtimestamp(b.gold_weekend_close(stamp(24, 6, 0)) / 1000, tz).hour, 23)

    def test_weekend_pause_no_false_data_push_or_trade_signal(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo('Europe/Zurich')
        def stamp(day, hour, minute, second=0):
            return int(datetime(2026, 10, day, hour, minute, second, tzinfo=tz).timestamp() * 1000)
        quote_at = stamp(9, 22, 59, 50)
        good = {**self.market, 'dataAt': quote_at}
        state, events = b.advance({}, self.settings, good, True, True, now=quote_at)
        self.assertEqual(events, [])
        bad = {**good, 'priceFresh': False, 'ready': False, 'price': 180}
        state, events = b.advance(state, self.settings, bad, True, True, now=stamp(9, 23, 1))
        self.assertEqual(events, [])
        self.assertEqual(state['dataStatus'], 'closed')
        self.assertTrue(state['continuedCalculation']['marketClosed'])
        state, events = b.advance(state, self.settings, bad, True, True, now=stamp(10, 6, 1))
        self.assertEqual(events, [])
        self.assertEqual(state['dataStatus'], 'closed')
        # A quote that looks fresh after close must not trigger target/stop messages.
        tempting = {**good, 'price': 180}
        state, events = b.advance(state, self.settings, tempting, True, True, now=stamp(10, 6, 2))
        self.assertNotIn('target', self.kinds(events))
        self.assertNotIn('signal-change', self.kinds(events))
        self.assertEqual(state['dataStatus'], 'closed')
        # Reopening without a fresh quote must eventually alert as a real outage.
        monday = datetime(2026, 10, 12, 0, 0, tzinfo=tz).timestamp() * 1000
        for offset, wanted in ((1, []), (31000, []), (61000, ['data-unavailable'])):
            state, events = b.advance(state, self.settings, bad, True, True, now=int(monday + offset))
            self.assertEqual(self.kinds(events), wanted)
        self.assertEqual(state['dataStatus'], 'unavailable')

    def test_weekend_pause_never_hides_old_preclose_failure(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        tz = ZoneInfo('Europe/Zurich')
        now = int(datetime(2026, 10, 10, 6, 0, tzinfo=tz).timestamp() * 1000)
        stale = {**self.market, 'ready': False, 'priceFresh': False,
                 'dataAt': int(datetime(2026, 10, 9, 19, 0, tzinfo=tz).timestamp() * 1000)}
        state, _ = b.advance({}, self.settings, stale, True, False, now=now)
        self.assertEqual(state['dataStatus'], 'unavailable')
        self.assertFalse(state['continuedCalculation']['marketClosed'])

    def test_stop_once_per_trade(self):
        m={**self.market,'price':89}
        s,e=b.advance({},self.settings,m,False,True);self.assertIn('stop-hit',self.kinds(e))
        self.assertEqual(b.advance(s,self.settings,m,False,True)[1],[])
        s,_=b.advance(s,self.settings,self.market,False,True)
        self.assertNotIn('stop-hit',self.kinds(b.advance(s,self.settings,m,False,True)[1]))
    def test_short_stop_and_target(self):
        self.settings['trade'].update(dir='SHORT',stop=110,target=70)
        _,e=b.advance({},self.settings,{**self.market,'price':111},False,True)
        self.assertIn('stop-hit',self.kinds(e))
        s,e=b.advance({},self.settings,{**self.market,'price':70},False,True)
        self.assertIn('target',self.kinds(e));self.assertNotIn('target',self.kinds(b.advance(s,self.settings,{**self.market,'price':69},False,True)[1]))
    def test_profit_stop_persisted_not_loosened(self):
        s,e=b.advance({},self.settings,{**self.market,'price':120},False,True)
        self.assertEqual(s['trade']['stop'],110);self.assertIn('profit-protection',self.kinds(e))
        s,e=b.advance(s,self.settings,{**self.market,'price':121},False,True)
        self.assertEqual(s['trade']['stop'],110);self.assertEqual(e,[])
    def test_reversal_and_weak_profit(self):
        s,e=b.advance({},self.settings,{**self.market,'price':111,'direction':'SHORT','mtf':'SHORT','score':20},False,True)
        self.assertIn('reversal',self.kinds(e));self.assertIn('profit-weak',self.kinds(e))
        self.assertEqual(b.advance(s,self.settings,{**self.market,'price':111,'direction':'SHORT','mtf':'SHORT','score':20},False,True)[1],[])
    def test_entry_filter_does_not_suppress_active_trade_reversal(self):
        market={**self.market,'direction':'NEUTRAL','baseDirection':'SHORT','mtf':'SHORT'}
        _,events=b.advance({},self.settings,market,True,True)
        self.assertIn('reversal',self.kinds(events))
        self.assertNotIn('signal-change',self.kinds(events))
    def test_data_outage_no_false_target_and_recovery(self):
        m={**self.market,'price':180,'priceFresh':False}
        s,e=b.advance({},self.settings,m,False,True,now=0);self.assertEqual(e,[])
        s,e=b.advance(s,self.settings,m,False,True,now=30000);self.assertEqual(e,[])
        s,e=b.advance(s,self.settings,m,False,True,now=60000);self.assertEqual(self.kinds(e),['data-unavailable'])
        s,e=b.advance(s,self.settings,self.market,False,True,now=90000);self.assertEqual(e,[])
        self.assertIn('data-recovered',self.kinds(b.advance(s,self.settings,self.market,False,True,now=120000)[1]))
    def test_general_without_trade_and_switch_off(self):
        s,e=b.advance({},self.settings,self.market,True,False,now=0)
        self.assertEqual(e,[])
        s,e=b.advance(s,self.settings,{**self.market,'dataAt':self.market['dataAt']+30000},True,False,now=30000)
        self.assertEqual(self.kinds(e),['signal-change']);self.assertNotIn('trade',s)
        self.assertEqual(b.advance(s,self.settings,self.market,True,False)[1],[])
        self.assertEqual(b.advance({},self.settings,self.market,False,False)[1],[])
    def test_trade_identity_and_validation(self):
        s,_=b.advance({},self.settings,{**self.market,'price':120},False,True)
        new=copy.deepcopy(self.settings);new['trade']['tradeId']='b'
        state,_=b.advance(s,new,self.market,False,True)
        self.assertEqual(state['trade']['stop'],90)
        with self.assertRaises(ValueError):b.config({'trade':{**new['trade'],'instrument':'GC=F'}})
        with self.assertRaises(ValueError):b.config({'trade':{**new['trade'],'initialRisk':0}})
    def test_target_extension_persists_and_protects_profit(self):
        self.settings['trade']['target']=120
        m={**self.market,'price':121,'macd':2,'signal':1,'suggestedTarget':140,'analysisBarAt':1000}
        state,events=b.advance({},self.settings,m,False,True)
        self.assertIn('target-extension',self.kinds(events))
        self.assertNotIn('target',self.kinds(events))
        self.assertEqual(state['trade']['target'],140)
        self.assertGreaterEqual(state['trade']['stop'],110)
        # An old browser snapshot cannot lower the persisted target or repeat it.
        again,events=b.advance(state,self.settings,m,False,True)
        self.assertEqual(again['trade']['target'],140)
        self.assertEqual(events,[])
        # Same closed bar cannot extend again even if its spot moves.
        _,events=b.advance(state,self.settings,{**m,'price':141,'suggestedTarget':160},False,True)
        self.assertNotIn('target-extension',self.kinds(events))
        _,events=b.advance(state,self.settings,{**m,'price':141,'suggestedTarget':160,'analysisBarAt':2000},False,True)
        self.assertIn('target-extension',self.kinds(events))

    def test_target_extension_requires_fresh_strong_confirmed_continuation(self):
        self.settings['trade']['target']=120
        m={**self.market,'price':121,'macd':2,'signal':1,'suggestedTarget':140,'analysisBarAt':1000}
        for change in ({'priceFresh':False},{'ready':False},{'direction':'SHORT'},{'mtf':'NEUTRAL'},{'macd':0},{'score':60},{'suggestedTarget':122},{'analysisBarAt':None}):
            _,events=b.advance({},self.settings,{**m,**change},False,True)
            self.assertNotIn('target-extension',self.kinds(events),change)

    def test_short_target_moves_lower_while_product_eur_target_rises(self):
        product=dict(isin='DE000FG4JXV7',direction='SHORT',simpleSpotTurbo=True,referenceConfirmed=True,currency='EUR',bid=20,goldReference=100,fxReference=.9,fxScenario=.9,ratio=.1,strike=160,ko=160,entry=21,quantity=10,source='fixture',referenceAt='02/10/2026 15:04')
        self.settings['trade'].update(dir='SHORT',stop=110,target=80,product=product)
        self.settings=b.config(self.settings)
        m={**self.market,'price':79,'direction':'SHORT','mtf':'SHORT','score':20,'macd':-2,'signal':-1,'suggestedTarget':60,'analysisBarAt':1000}
        state,events=b.advance({},self.settings,m,False,True)
        self.assertEqual(state['trade']['target'],60)
        self.assertLessEqual(state['trade']['stop'],90)
        extension=next(e for e in events if e['data']['eventKind']=='target-extension')
        self.assertIn('23.6000 EUR/Stück',extension['body'])
        self.assertIn(product['isin'],extension['body']);self.assertIn(product['referenceAt'],extension['body'])
        self.assertIn('geschätzt',extension['body'])
        self.assertIsNone(b.product_price(product,160))
        with self.assertRaises(ValueError):b.product_model({**product,'direction':'LONG'},'SHORT')
        with self.assertRaises(ValueError):b.product_model({**product,'ratio':0},'SHORT')

    def test_actual_dashboard_runtime_and_missing_data(self):
        import time,math
        now=int(time.time()*1000);bars={}
        for tf,step in [('5m',300000),('15m',900000),('1h',3600000),('4h',14400000)]:
            end=now//step*step
            bars[tf]=[dict(openTime=end-(240-i)*step,open=4000+i*.1,high=4004+i*.1,low=3996+i*.1,close=4000+i*.1+math.sin(i/8),instrument='XAU/USD',isOpen=False) for i in range(240)]
        from datetime import datetime,timezone
        bundle={'spots':{'xaus':4024,'is_genuine_xauusd_spot':True,'spot_price_as_of':datetime.now(timezone.utc).isoformat()},'history':{'bars_by_tf':bars}}
        result=b.analyze(bundle,self.settings)
        self.assertTrue(result['ready']);self.assertTrue(result['priceFresh']);self.assertIn('score',result)
        self.assertFalse(b.analyze({},self.settings)['ready'])
        for update in ({'is_genuine_xauusd_spot':False}, {'spot_error':'offline'},
                       {'spot_price_as_of':datetime.fromtimestamp(time.time()-61,timezone.utc).isoformat()}):
            bad={**bundle,'spots':{**bundle['spots'],**update}}
            self.assertFalse(b.analyze(bad,self.settings)['priceFresh'])


class BackgroundDelivery(PushMonitorTests):
    def test_delayed_test_is_persisted_and_authenticated(self):
        db,conn=self.connection();conn.execute.return_value.fetchone.return_value=(True,False)
        with patch.object(push_server,'db',db),patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'webpush') as send:
            self.assertEqual(self.request('/test-background',{'endpoint':'fixture'},'wrong')[0],401)
            status,result=self.request('/test-background',{'endpoint':'fixture'})
            self.assertEqual(status,200);self.assertGreater(result['dueAt'],push_server.time.time()*1000)
            send.assert_not_called()
    def test_trigger_messages_use_real_rules(self):
        for stage,kind in ((0,'target'),(1,'stop-hit')):
            message=push_server.trigger_test_message(stage,1800000000000)
            self.assertEqual(message['data']['eventKind'],kind)
            self.assertTrue(message['data']['test'])
            self.assertTrue(message['title'].startswith('TEST'))

    def test_target_schedules_stop_without_touching_real_trade(self):
        db,conn=self.connection()
        pending=dict(kind='general',scenario='stop-target',stage=0,dueAt=int(push_server.time.time()*1000)-1)
        conn.execute.return_value.fetchall.return_value=[(1,{},pending,True,False)]
        with patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush') as send:
            push_server.deliver_background_tests()
            self.assertEqual(json.loads(send.call_args.kwargs['data'])['data']['eventKind'],'target')
            updates=[c for c in conn.execute.call_args_list if c.args[0].startswith('UPDATE')]
            self.assertEqual(len(updates),1)
            self.assertIn('SET pending_test=',updates[0].args[0])
            self.assertEqual(json.loads(updates[0].args[1][0])['stage'],1)

    def test_delayed_delivery_needs_no_open_browser(self):
        db,conn=self.connection();conn.execute.return_value.fetchall.return_value=[(1,{},dict(kind='general',dueAt=int(push_server.time.time()*1000)-1),True,False)]
        with patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush') as send:
            push_server.deliver_background_tests();send.assert_called_once()
            self.assertTrue(json.loads(send.call_args.kwargs['data'])['data']['test'])
            self.assertTrue(any('pending_test=NULL' in c.args[0] for c in conn.execute.call_args_list))

    def test_background_failure_keeps_checkpoint_and_success_persists(self):
        db,conn=self.connection();settings=b.config({})
        conn.execute.return_value.fetchall.return_value=[(1,{},True,False,False,settings,{'signalPending':{'direction':'LONG','since':0,'dataAt':1}},None,None)]
        market={'ready':True,'priceFresh':True,'direction':'LONG','mtf':'LONG','dataAt':1800000000000}
        with patch.object(push_server.rule_learning,'tick'),patch.object(push_server.rule_learning,'policy',return_value={}),patch.object(push_server,'db',db),patch.object(push_server.background_push,'analyze',return_value=market),patch.object(push_server,'vapid',return_value='x'),patch.object(push_server,'webpush',side_effect=push_server.WebPushException('fail')):
            self.assertEqual(push_server.run_background({}),0)
            self.assertFalse(any('UPDATE subscriptions SET background_state' in c.args[0] for c in conn.execute.call_args_list))
        with patch.object(push_server.rule_learning,'tick'),patch.object(push_server.rule_learning,'policy',return_value={}),patch.object(push_server,'db',db),patch.object(push_server.background_push,'analyze',return_value=market),patch.object(push_server,'vapid',return_value='x'),patch.object(push_server,'webpush'):
            self.assertEqual(push_server.run_background({}),1)
            self.assertTrue(any('UPDATE subscriptions SET background_state' in c.args[0] for c in conn.execute.call_args_list))

if __name__=='__main__':unittest.main()

class IntradayEndTests(unittest.TestCase):
 def test_daily_reminder_once_even_without_prices(self):
  settings=b.config({'trade':{'active':True,'tradeId':'end','instrument':'XAU/USD','dir':'LONG','entry':100,'stop':90,'initialRisk':10}})
  market={'ready':False,'priceFresh':False,'session':{'closeReminder':True,'date':'2026-10-05'}}
  state,events=b.advance({},settings,market,False,True)
  self.assertIn('intraday-end',[e['data']['eventKind'] for e in events])
  self.assertEqual(b.advance(state,settings,market,False,True)[1],[])
  self.assertEqual(b.advance({},settings,market,False,False)[1],[])

class DisconnectedHttpTests(unittest.TestCase):
    def test_closed_socket_is_not_retried_as_an_internal_push_failure(self):
        from unittest.mock import Mock
        for stage in ('end_headers','write'):
            for error in (BrokenPipeError(),ConnectionResetError()):
                h=Mock();h.headers={}
                getattr(h if stage=='end_headers' else h.wfile,stage).side_effect=error
                push_server.send_json(h,200,{'ok':True})
                h.send_response.assert_called_once_with(200)
                self.assertTrue(h.close_connection)
        h=Mock();h.headers={};h.wfile.write.side_effect=ValueError('real bug')
        with self.assertRaises(ValueError):push_server.send_json(h,200,{'ok':True})

    def test_request_disconnect_does_not_generate_second_response(self):
        from unittest.mock import Mock
        h=object.__new__(push_server.Handler);h.path='/decision-audit/read';h.headers={'X-Bob-Push-Token':'test'}
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test'),patch.object(push_server,'json_body',side_effect=ConnectionResetError()),patch.object(push_server,'send_json') as send:
            h.do_POST();send.assert_not_called();self.assertTrue(h.close_connection)

