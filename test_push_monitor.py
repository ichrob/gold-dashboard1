import http.client
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
import push_server
from fibonacci_monitor import validate_monitor, LEVELS

class PushMonitorTests(unittest.TestCase):
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
    def test_product_recommendations_never_reach_delivery(self):
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'webpush') as send,patch.object(push_server,'db') as database:
            for data in ({'isin':'DE000FG4JXV7'}, {'kind':'product-selection','approved':True}, {'kind':'best-trade'}):
                status,result=self.request('/send',{'title':'Bob Auswahl','data':data})
                self.assertEqual(status,200);self.assertEqual(result['sent'],0)
            send.assert_not_called();database.assert_not_called()
    def test_endpoints_require_server_token(self):
        for path in ('/monitor','/preferences','/auth-session/create','/auth-session/check','/auth-session/revoke','/market-spots/read','/market-spots/write'):
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
    def test_failed_delivery_does_not_advance(self):
        monitor,payload=self.monitor();db,conn=self.connection();conn.execute.return_value.fetchall.return_value=[(123,{},monitor)]
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test-token'),patch.object(push_server,'db',db),patch.object(push_server,'vapid',return_value='fixture'),patch.object(push_server,'webpush',side_effect=push_server.WebPushException('fixture')):
            self.assertEqual(self.request('/monitor',payload)[1]['sent'],0)
            self.assertFalse(any('UPDATE subscriptions SET trade_monitor=' in c.args[0] for c in conn.execute.call_args_list))

if __name__=='__main__':unittest.main()
