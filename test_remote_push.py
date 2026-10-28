import json
import os
import unittest
from unittest.mock import Mock
import bob_mcp
import bob_oauth_store as oauth
import remote_push as rp


class RemotePushTests(unittest.TestCase):
    def request(self,name,args):return {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}}
    def test_discovery_annotations_and_separate_consent(self):
        tools=bob_mcp.tool_definitions(diagnostics=True,remote_push=True)
        t=next(t for t in tools if t['name']=='bob_push_test')
        self.assertFalse(t['annotations']['readOnlyHint'])
        self.assertEqual(t['securitySchemes'][0]['scopes'],[rp.SCOPE])
        self.assertTrue(oauth.valid_scope(rp.SCOPE))
        self.assertFalse(oauth.valid_scope('bob:orders:write'))
        request=self.request('bob_push_test',{'deviceId':'device-1','requestId':'a'*32})
        reader=Mock(side_effect=AssertionError('must not execute'))
        _,response=bob_mcp.handle(request,reader,reader,remote_push=True,push_reader=reader)
        self.assertTrue(response['result']['isError'])
        self.assertIn(rp.SCOPE,response['result']['_meta']['mcp/www_authenticate'][0])
        reader.assert_not_called()
        sender=Mock(return_value={'status':'scheduled'})
        _,response=bob_mcp.handle(request,reader,remote_push=True,push_sender=sender)
        self.assertEqual(json.loads(response['result']['content'][0]['text'])['status'],'scheduled')
        sender.assert_called_once()

    def test_arbitrary_text_and_unknown_devices_cannot_be_submitted(self):
        for args in ({'deviceId':'device-1','requestId':'a'*32,'body':'Buy now'},
                     {'deviceId':'https://push.example','requestId':'a'*32},
                     {'deviceId':'device-1','requestId':'bad'}):
            with self.assertRaises(ValueError):rp.arguments('bob_push_test',args)

    def test_device_list_never_exposes_endpoint(self):
        from datetime import datetime,timezone
        conn=Mock();conn.execute.return_value.fetchall.return_value=[(7,True,False,datetime.now(timezone.utc),False)]
        result=rp.devices(conn)
        self.assertEqual(result['devices'][0]['deviceId'],'device-7')
        self.assertNotIn('endpoint',json.dumps(result))
        self.assertFalse(result['realOrders'])


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'isolated PostgreSQL not configured')
class RemotePushDatabaseTests(unittest.TestCase):
    def test_idempotency_rate_limit_disable_expiry_and_receipt_correlation(self):
        import psycopg
        from datetime import datetime,timezone
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE subscriptions(id BIGINT PRIMARY KEY,general_enabled BOOLEAN,trade_enabled BOOLEAN,pending_test JSONB,updated_at TIMESTAMPTZ) ON COMMIT DROP')
            conn.execute('CREATE TEMP TABLE bob_remote_push_tests(request_id TEXT PRIMARY KEY,device_id BIGINT,created_at BIGINT,due_at BIGINT,outcome TEXT DEFAULT \'scheduled\',last_attempt_at BIGINT) ON COMMIT DROP')
            conn.execute('CREATE TEMP TABLE bob_diagnostic_history(trace_id TEXT,stage TEXT,payload JSONB) ON COMMIT DROP')
            conn.execute('INSERT INTO subscriptions VALUES(1,TRUE,FALSE,NULL,now()),(2,FALSE,FALSE,NULL,now())')
            now=1000000;args={'deviceId':'device-1','requestId':'a'*32}
            self.assertEqual(rp.schedule(conn,args,now)['status'],'scheduled')
            self.assertTrue(rp.schedule(conn,args,now)['reused'])
            self.assertEqual(conn.execute('SELECT count(*) FROM bob_remote_push_tests').fetchone()[0],1)
            self.assertEqual(rp.schedule(conn,{'deviceId':'device-1','requestId':'b'*32},now)['status'],'test-already-pending')
            conn.execute('UPDATE subscriptions SET pending_test=NULL WHERE id=1')
            self.assertEqual(rp.schedule(conn,{'deviceId':'device-1','requestId':'b'*32},now+1)['status'],'rate-limited')
            self.assertEqual(rp.schedule(conn,{'deviceId':'device-2','requestId':'b'*32},now)['status'],'channels-disabled')
            self.assertEqual(rp.schedule(conn,{'deviceId':'device-99','requestId':'b'*32},now)['status'],'device-not-found')
            with self.assertRaises(ValueError):rp.schedule(conn,{'deviceId':'device-2','requestId':'a'*32},now)
            rp.record(conn,{'remoteRequestId':'a'*32},'provider-accepted',now+30000)
            conn.execute('INSERT INTO bob_diagnostic_history VALUES(%s,%s,%s::jsonb)',('a'*32,'push-delivery',json.dumps({'receiptId':'receipt-a','outcome':'provider-accepted'})))
            conn.execute('INSERT INTO bob_diagnostic_history VALUES(%s,%s,%s::jsonb)',('other','push-delivery',json.dumps({'receiptId':'receipt-a','outcome':'browser-receipt','receiptState':'show-resolved'})))
            result=rp.status(conn,{'requestId':'a'*32})
            self.assertTrue(result['browserApiAccepted'])
            self.assertFalse(result['notificationClicked'])
            self.assertFalse(result['visibleAndroidDeliveryVerified'])
            self.assertEqual(result['status'],'provider-accepted')

if __name__=='__main__':unittest.main()
