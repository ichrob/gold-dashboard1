import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import Mock, patch
import android_remote as a
import android_remote_http as http
import bob_mcp
import bob_oauth_store as oauth
from test_android_telemetry import Handler

def report():return dict(version=10222,running=False,serviceConnected=True,report={'DIRECT_ROOT':1},ackId=None,ackCode=None)

class Boundary(unittest.TestCase):
    def test_old_scopes_never_grant_remote_control(self):
        self.assertTrue(oauth.valid_scope(a.SCOPE))
        self.assertFalse(oauth.valid_scope('bob:orders:write'))
        for name,args in [('bob_handy_sessions',{}),('bob_handy_action',dict(sessionId='a'*24,requestId='b'*32,action='READ_PAGE'))]:
            request=dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name=name,arguments=args))
            reader=Mock(side_effect=AssertionError('must not execute'))
            _,r=bob_mcp.handle(request,reader,reader,remote_handy=True)
            self.assertTrue(r['result']['isError']);self.assertIn(a.SCOPE,r['result']['_meta']['mcp/www_authenticate'][0]);reader.assert_not_called()
            callback=Mock(return_value={'ok':True})
            _,r=bob_mcp.handle(request,reader,remote_handy=True,handy_callback=callback)
            self.assertFalse(r['result']['isError']);callback.assert_called_once_with(name,args)
        for t in bob_mcp.tool_definitions(remote_handy=True):
            if t['name'] in a.TOOLS:self.assertEqual(t['securitySchemes'][0]['scopes'],[a.SCOPE])
    def test_unknown_actions_extra_data_and_raw_reports_rejected(self):
        for action in ('BUY','CLICK','LOGIN','OPEN_URL','SET_TEXT',''):
            with self.assertRaises(ValueError):a.arguments('bob_handy_action',dict(sessionId='a'*24,requestId='b'*32,action=action))
        for key,value in [('screen','secret'),('report',{'account':500}),('report',{'DIRECT_ROOT':True}),('version',True),('ackCode','raw')]:
            r=report();r[key]=value
            with self.assertRaises(ValueError):a.snapshot(r)
    def test_device_cannot_pair_or_schedule_and_cookie_cannot_poll(self):
        for path,body,auth,headers,expected in [
            ('pair',{'tokenHash':'a'*64},False,{'Authorization':'Bearer '+'b'*64},401),
            ('device',{'op':'poll','snapshot':report()},True,{},401),
            ('device',{'op':'command','arguments':{}},False,{'Authorization':'Bearer '+'b'*64},400),
            ('device',{'op':'poll','token':'c'*64,'snapshot':report()},False,{'Authorization':'Bearer '+'b'*64},400)]:
            h=Handler(body,auth,headers);http.route(h,'POST','/api/android-remote/'+path,lambda _:self.fail('forwarded'));self.assertEqual(h.code,expected)
        h=Handler({'tokenHash':'a'*64},True)
        with patch('bob_auth.same_origin',return_value=False):http.route(h,'POST','/api/android-remote/pair',lambda _:self.fail('forwarded'))
        self.assertEqual(h.code,403)
        sent=[];h=Handler({'op':'poll','snapshot':report()},headers={'Authorization':'Bearer '+'b'*64})
        http.route(h,'POST','/api/android-remote/device',lambda p:sent.append(p) or {'ok':True})
        self.assertEqual(sent[0]['token'],'b'*64);self.assertEqual(h.code,200)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL not configured')
class Database(unittest.TestCase):
    def test_pairing_expiry_at_most_once_ack_stop_and_revocation(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            try:
                schema='android_remote_'+uuid.uuid4().hex
                conn.execute('CREATE SCHEMA '+schema);conn.execute('SET LOCAL search_path TO '+schema);a.init(conn)
                now=1000000;token='a'*64;digest=hashlib.sha256(token.encode()).hexdigest()
                def call(p,at=now):return a.handle(conn,p,at)
                poll={'op':'poll','token':token,'snapshot':report()}
                with self.assertRaises(PermissionError):call(poll)
                session=call({'op':'pair','tokenHash':digest});sid=session['sessionId']
                self.assertEqual(call({'op':'pair','tokenHash':digest},now+100)['expiresAt'],session['expiresAt'])
                args=dict(sessionId=sid,requestId='b'*32,action='READ_PAGE');cmd={'op':'command','arguments':args}
                with self.assertRaises(ValueError):call(cmd)
                self.assertIsNone(call(poll)['command'])
                self.assertEqual(call(cmd)['status'],'QUEUED');self.assertTrue(call(cmd)['reused'])
                with self.assertRaises(ValueError):call({'op':'command','arguments':{**args,'action':'STOP'}})
                delivered=call(poll)['command'];self.assertEqual(delivered['requestId'],args['requestId'])
                self.assertIsNone(call(poll)['command'])
                self.assertEqual(call(cmd)['status'],'DELIVERED')
                r={**report(),'ackId':args['requestId'],'ackCode':'STARTED'}
                call({**poll,'snapshot':r});self.assertEqual(call(cmd)['status'],'STARTED')
                self.assertNotIn(token,json.dumps(call({'op':'sessions'})))
                with self.assertRaises(ValueError):call({'op':'command','arguments':{**args,'requestId':'c'*32}},now+31000)
                call(poll,now+32000)
                call({'op':'command','arguments':{**args,'requestId':'c'*32}},now+32000)
                call({'op':'command','arguments':{**args,'requestId':'d'*32,'action':'STOP'}},now+32001)
                self.assertEqual(call(poll,now+32002)['command']['action'],'STOP')
                self.assertIsNone(call(poll,now+32003)['command'])
                call({'op':'revoke','token':token},now+32004)
                with self.assertRaises(PermissionError):call(poll,now+32005)
                with self.assertRaises(PermissionError):call({'op':'pair','tokenHash':digest},now+32006)
                token2='e'*64;digest2=hashlib.sha256(token2.encode()).hexdigest()
                call({'op':'pair','tokenHash':digest2})
                with self.assertRaises(PermissionError):call({**poll,'token':token2},now+900000)
            finally:conn.rollback()
