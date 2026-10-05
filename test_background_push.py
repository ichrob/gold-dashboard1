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
    def test_stop_once_and_rearm(self):
        m={**self.market,'price':89}
        s,e=b.advance({},self.settings,m,False,True);self.assertIn('stop-hit',self.kinds(e))
        self.assertEqual(b.advance(s,self.settings,m,False,True)[1],[])
        s,_=b.advance(s,self.settings,self.market,False,True)
        self.assertIn('stop-hit',self.kinds(b.advance(s,self.settings,m,False,True)[1]))
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
    def test_data_outage_no_false_target_and_recovery(self):
        m={**self.market,'price':180,'priceFresh':False}
        s,e=b.advance({},self.settings,m,False,True);self.assertEqual(self.kinds(e),['data-unavailable'])
        self.assertEqual(b.advance(s,self.settings,m,False,True)[1],[])
        self.assertIn('data-recovered',self.kinds(b.advance(s,self.settings,self.market,False,True)[1]))
    def test_general_without_trade_and_switch_off(self):
        s,e=b.advance({},self.settings,self.market,True,False)
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
        self.assertIn('target',self.kinds(events))
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
        self.assertIn('berechnet',extension['body'])
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
    def test_delayed_delivery_needs_no_open_browser(self):
        db,conn=self.connection();conn.execute.return_value.fetchall.return_value=[(1,{},dict(kind='general',dueAt=int(push_server.time.time()*1000)-1),True,False)]
        with patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush') as send:
            push_server.deliver_background_tests();send.assert_called_once()
            self.assertTrue(json.loads(send.call_args.kwargs['data'])['data']['test'])
            self.assertTrue(any('pending_test=NULL' in c.args[0] for c in conn.execute.call_args_list))

    def test_background_failure_keeps_checkpoint_and_success_persists(self):
        db,conn=self.connection();settings=b.config({})
        conn.execute.return_value.fetchall.return_value=[(1,{},True,False,False,settings,{},None,None)]
        market={'ready':True,'priceFresh':True,'direction':'LONG','mtf':'LONG','dataAt':1800000000000}
        with patch.object(push_server,'db',db),patch.object(push_server.background_push,'analyze',return_value=market),patch.object(push_server,'vapid',return_value='x'),patch.object(push_server,'webpush',side_effect=push_server.WebPushException('fail')):
            self.assertEqual(push_server.run_background({}),0)
            self.assertFalse(any('UPDATE subscriptions SET background_state' in c.args[0] for c in conn.execute.call_args_list))
        with patch.object(push_server,'db',db),patch.object(push_server.background_push,'analyze',return_value=market),patch.object(push_server,'vapid',return_value='x'),patch.object(push_server,'webpush'):
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
