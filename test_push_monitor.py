import http.client
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
import push_server
from fibonacci_monitor import validate_monitor, LEVELS

class PushMonitorTests(unittest.TestCase):
    def test_startup_skips_existing_column_locks_and_preserves_key(self):
        database, conn = self.connection()
        columns = ('general_enabled', 'trade_enabled', 'active_trade', 'trade_monitor',
                   'product_selection', 'background_config', 'background_state',
                   'selection_evidence', 'pending_test')
        conn.execute.return_value.fetchall.return_value = [(c,) for c in columns]
        conn.execute.return_value.fetchone.return_value = ('existing-key',)
        with patch.object(push_server, 'db', database), patch.object(push_server, 'Vapid') as key:
            push_server.init_db()
        statements = [c.args[0] for c in conn.execute.call_args_list]
        self.assertFalse(any('ALTER TABLE subscriptions' in s for s in statements))
        key.assert_not_called()
        conn.commit.assert_called_once()
        conn.reset_mock()
        conn.execute.return_value.fetchall.return_value = [(c,) for c in columns if c != 'pending_test']
        with patch.object(push_server, 'db', database):
            push_server.init_db()
        alterations = [c.args[0] for c in conn.execute.call_args_list if 'ALTER TABLE subscriptions' in c.args[0]]
        self.assertEqual(alterations, ['ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS pending_test JSONB'])

    def test_startup_transient_lock_retry_is_bounded(self):
        lock = push_server.psycopg.errors.LockNotAvailable('fixture')
        with patch.object(push_server, '_init_db_once', side_effect=[lock, None]) as run, patch.object(push_server.time, 'sleep') as sleep:
            push_server.init_db()
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(1)
        with patch.object(push_server, '_init_db_once', side_effect=lock) as run, patch.object(push_server.time, 'sleep'):
            with self.assertRaises(push_server.psycopg.errors.LockNotAvailable):
                push_server.init_db()
            self.assertEqual(run.call_count, 3)
        with patch.object(push_server, '_init_db_once', side_effect=ValueError('schema')) as run, patch.object(push_server.time, 'sleep') as sleep:
            with self.assertRaises(ValueError):
                push_server.init_db()
            run.assert_called_once()
            sleep.assert_not_called()

    @classmethod
    def setUpClass(cls):
        cls.httpd=push_server.ThreadingHTTPServer(('127.0.0.1',0),push_server.Handler)
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()
        cls.port=cls.httpd.server_address[1]
    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join()
    def request(self,path,payload,token='test-token'):
        conn=http.client.HTTPConnection('127.0.0.1',self.port)
        conn.request('POST',path,json.dumps(payload),{'Content-Type':'application/json','X-Bob-Push-Token':token})
        response=conn.getresponse();result=response.status,json.loads(response.read());conn.close();return result
    def connection(self):
        db=MagicMock();conn=db.return_value.__enter__.return_value
        return db,conn
    def monitor(self):
        now=push_server.fibonacci_monitor.time.time()*1000
        step=300000;end=int(now//step)*step
        payload=dict(tradeId='trade-fixture',direction='LONG',timeframe='5m',instrument='XAU/USD',levels={k:4050 for k in LEVELS},startedAt=end-step,previousClose=4040)
        return validate_monitor(payload,now),dict(barsByTf={'5m':[dict(openTime=end-step,close=4060,isOpen=False,instrument='XAU/USD')]})
    def test_provider_timeout_is_bounded_and_preserves_retry(self):
        from requests.exceptions import Timeout
        with patch.object(push_server, '_webpush', side_effect=Timeout('fixture')) as send:
            with self.assertRaises(push_server.WebPushException):
                push_server.webpush(subscription_info={})
            self.assertEqual(send.call_args.kwargs['timeout'], 8)

    def test_database_waits_are_bounded(self):
        with patch.object(push_server, 'DATABASE_URL', 'fixture'), patch.object(push_server.psycopg, 'connect') as connect:
            push_server.db()
            self.assertEqual(connect.call_args.kwargs['connect_timeout'], 5)
            self.assertIn('lock_timeout=3000', connect.call_args.kwargs['options'])

    def test_selection_off_does_not_evaluate_or_send(self):
        db,conn=self.connection();conn.execute.return_value.fetchone.return_value=(False,)
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server.product_push,'evaluate') as verify,patch.object(push_server,'webpush') as send:
            status,result=self.request('/selection',{'endpoint':'fixture','approved':True})
            self.assertEqual(status,200);self.assertTrue(result['disabled'])
            verify.assert_not_called();send.assert_not_called()
    def test_selection_is_rechecked_and_targets_only_enabled_device(self):
        db,conn=self.connection();sub={'endpoint':'fixture'}
        conn.execute.return_value.fetchone.side_effect=[(True,),(123,sub,None)]
        now=int(push_server.time.time()*1000)
        checked={'products':[{'isin':'DE000FG4JXV7','name':'Turbo','direction':'SHORT','scope':'XAU/USD','reasons':['KO-Puffer ausreichend']}], 'expiresAt':now+25000}
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server.product_push,'evaluate',return_value=checked) as verify,patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush') as send:
            status,result=self.request('/selection',{'endpoint':'fixture'})
            self.assertEqual(status,200);self.assertEqual(result['sent'],1)
            verify.assert_called_once();send.assert_called_once()
            self.assertEqual(send.call_args.kwargs['subscription_info'],sub)
            self.assertLessEqual(send.call_args.kwargs['ttl'],25)
            self.assertTrue(any('general_enabled=TRUE FOR UPDATE' in c.args[0] for c in conn.execute.call_args_list))
    def test_switch_off_during_verification_blocks_delivery(self):
        db,conn=self.connection();conn.execute.return_value.fetchone.side_effect=[(True,),None]
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server.product_push,'evaluate',return_value={'products':[]}),patch.object(push_server,'webpush') as send:
            status,result=self.request('/selection',{'endpoint':'fixture'})
            self.assertEqual(status,200);self.assertTrue(result['disabled']);send.assert_not_called()
    def test_failed_product_delivery_does_not_consume_transition(self):
        _,conn=self.connection();now=int(push_server.time.time()*1000)
        checked={'products':[{'isin':'fixture','direction':'LONG','scope':'XAU/USD'}], 'expiresAt':now+25000}
        with patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush',side_effect=push_server.WebPushException('fixture')):
            self.assertEqual(push_server.deliver_product_selection(conn,(1,{},None),checked),0)
            conn.execute.assert_not_called()
    def test_product_recommendations_never_reach_delivery(self):
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'webpush') as send,patch.object(push_server,'db') as database:
            for data in ({'isin':'DE000FG4JXV7'}, {'kind':'product-selection','approved':True}, {'kind':'best-trade'}):
                status,result=self.request('/send',{'title':'Bob Auswahl','data':data})
                self.assertEqual(status,200);self.assertEqual(result['sent'],0)
            send.assert_not_called();database.assert_not_called()
    def test_endpoints_require_server_token(self):
        for path in ('/selection','/monitor','/preferences','/auth-session/create','/auth-session/check','/auth-session/revoke','/market-spots/read','/market-spots/write'):
            status,_=self.request(path,{},'wrong');self.assertEqual(status,401)
    def test_session_route_is_authenticated_and_committed(self):
        db,conn=self.connection()
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server.bob_session_store,'handle',return_value={'ok':True}) as handle:
            status,result=self.request('/auth-session/revoke',{'tokenHash':'a'*64})
            self.assertEqual(status,200);self.assertTrue(result['ok'])
            handle.assert_called_once_with(conn,'revoke',{'tokenHash':'a'*64});conn.commit.assert_called_once()
    def test_preferences_preserve_checkpoint_and_stop(self):
        monitor,_=self.monitor();old={**monitor,'previousClose':4060,'processedAt':monitor['startedAt']+300000}
        db,conn=self.connection();conn.execute.return_value.fetchone.return_value=(old,)
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db):
            status,res=self.request('/preferences',dict(endpoint='fixture',activeTrade=True,trade=True,fibonacciMonitor=monitor))
            self.assertEqual(status,200);self.assertEqual(res['fibonacciMonitor'],'active')
            params=conn.execute.call_args.args[1];self.assertEqual(json.loads(params[3])['processedAt'],old['processedAt'])
            status,res=self.request('/preferences',dict(endpoint='fixture',activeTrade=False,trade=True))
            self.assertEqual(res['fibonacciMonitor'],'inactive');self.assertIsNone(conn.execute.call_args.args[1][3])
    def test_unknown_subscription_not_confirmed(self):
        db,conn=self.connection();conn.execute.return_value.fetchone.return_value=None
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db):
            self.assertEqual(self.request('/preferences',dict(endpoint='fixture',activeTrade=False))[0],400)
    def test_delivery_targets_subscription_and_saves_checkpoint(self):
        monitor,payload=self.monitor();db,conn=self.connection();sub={'endpoint':'https://example.test/fixture'}
        conn.execute.return_value.fetchall.return_value=[(123,sub,monitor)]
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush') as send:
            status,res=self.request('/monitor',payload)
            self.assertEqual(status,200);self.assertEqual(res['sent'],1);send.assert_called_once()
            self.assertEqual(send.call_args.kwargs['subscription_info'],sub)
            data=json.loads(send.call_args.kwargs['data'])
            self.assertEqual(len(data['data']['events']),6);self.assertIn('Kerzenschluss',data['body'])
            self.assertTrue(any('UPDATE subscriptions SET trade_monitor=' in c.args[0] for c in conn.execute.call_args_list))
    def test_data_outage_once_and_recovery(self):
        monitor,payload=self.monitor();db,conn=self.connection()
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush') as send:
            conn.execute.return_value.fetchall.return_value=[(123,{},monitor)]
            self.assertEqual(self.request('/monitor',{'barsByTf':{}})[1]['sent'],1)
            self.assertIn('eingeschränkt',json.loads(send.call_args.kwargs['data'])['body'])
            monitor['dataHealth']='unavailable'
            self.assertEqual(self.request('/monitor',{'barsByTf':{}})[1]['sent'],0)
            monitor['previousClose']=4060
            self.assertEqual(self.request('/monitor',payload)[1]['sent'],1)
            self.assertIn('keine Entwarnung',json.loads(send.call_args.kwargs['data'])['body'])

    def test_failed_delivery_does_not_advance(self):
        monitor,payload=self.monitor();db,conn=self.connection();conn.execute.return_value.fetchall.return_value=[(123,{},monitor)]
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush',side_effect=push_server.WebPushException('fixture')):
            self.assertEqual(self.request('/monitor',payload)[1]['sent'],0)
            self.assertFalse(any('UPDATE subscriptions SET trade_monitor=' in c.args[0] for c in conn.execute.call_args_list))

if __name__=='__main__':unittest.main()
