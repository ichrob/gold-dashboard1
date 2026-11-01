import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch
import android_remote as r
import android_telemetry as t
import android_telemetry_http as http
import bob_mcp
from test_android_telemetry import Handler

NOW=2000000000
ID='a'*32
ISIN='DE000FE2JJ20'
def value(active=True):
    return {'sessionId':ID,'active':active,'expiresAt':NOW+900,'observation':{'at':NOW,'code':'SEARCH','nodeCount':3,'isins':[],'draft':'','diagnostics':''},'ack':None}
def command(action='search_gold'):
    return dict(deviceId='b'*12,sessionId=ID,requestId=uuid.uuid4().hex,action=action)
class Protocol(unittest.TestCase):
    def state(self):return r.exchange({},value(),NOW)[0]
    def test_commands_reject_free_text_order_invalid_identity(self):
        for a in [dict(command(),action='buy'),dict(command(),text='password'),dict(command('search_isin'),isin='DE000FE2JJ21'),dict(command(),isin=ISIN),dict(command(),sessionId='')]:
            with self.assertRaises(ValueError):r.arguments('bob_phone_command',a)
        self.assertTrue(r.valid_isin(ISIN))
        r.arguments('bob_phone_command',dict(command('search_isin'),isin=ISIN))
    def test_queue_delivery_ack_and_no_replay(self):
        s=self.state();a=command();self.assertEqual(r.enqueue(s,a,NOW)['status'],'queued')
        s,out=r.exchange(s,value(),NOW+1);self.assertEqual(out['command']['requestId'],a['requestId'])
        self.assertEqual(r.enqueue(s,a,NOW+1)['status'],'delivered')
        self.assertIsNone(r.exchange(s,value(),NOW+2)[1]['command'])
        v=value();v['ack']={'requestId':a['requestId'],'code':'ACTION_ACCEPTED'}
        s,_=r.exchange(s,v,NOW+3)
        self.assertEqual(s['commands'][0]['status'],'acknowledged')
        self.assertEqual(r.enqueue(s,a,NOW+4)['status'],'acknowledged')
        with self.assertRaises(ValueError):r.enqueue(s,dict(a,action='read_page'),NOW+4)
    def test_expired_offline_busy_and_stop(self):
        s=self.state();a=command();r.enqueue(s,a,NOW)
        self.assertEqual(r.enqueue(s,command(),NOW)['status'],'busy')
        stop=command('stop');r.enqueue(s,stop,NOW+1)
        self.assertEqual(s['commands'][0]['status'],'cancelled')
        self.assertEqual(r.exchange(s,value(),NOW+2)[1]['command']['action'],'stop')
        self.assertEqual(r.enqueue(s,command(),NOW+33)['status'],'session-offline')
        s=self.state();r.enqueue(s,a,NOW)
        delayed=value();delayed['observation']['at']=NOW+91
        self.assertIsNone(r.exchange(s,delayed,NOW+91)[1]['command'])
        s=self.state();r.enqueue(s,a,NOW)
        s,out=r.exchange(s,value(False),NOW+1)
        self.assertIsNone(out['command']);self.assertEqual(s['commands'][0]['status'],'expired')
    def test_background_poll_after_45_seconds_still_delivers_short_lease(self):
        # The user can have DEGIRO in the foreground while Android delays
        # background polling. Queueing is not permission for 90s of execution.
        s=self.state();a=command('inspect')
        r.enqueue(s,a,NOW)
        self.assertEqual(s['commands'][0]['expiresAt'],NOW+r.QUEUE_TTL)
        v=value();v['observation']['at']=NOW+45
        s,response=r.exchange(s,v,NOW+45)
        delivered=response['command']
        self.assertEqual(delivered['requestId'],a['requestId'])
        self.assertEqual(delivered['expiresAt'],NOW+45+r.DELIVERY_LEASE)
        self.assertLessEqual(delivered['expiresAt']-(NOW+45),30)
        self.assertEqual(s['commands'][0]['status'],'delivered')
        self.assertEqual(s['commands'][0]['expiresAt'],NOW+r.QUEUE_TTL)
        # Reconnect/duplicate polling cannot repeat the already delivered
        # command. Late acknowledgements are linked to the same request.
        v['observation']['at']=NOW+46
        self.assertIsNone(r.exchange(s,v,NOW+46)[1]['command'])
        v['ack']={'requestId':a['requestId'],'code':'SEARCH'}
        v['observation']['at']=NOW+50
        s,_=r.exchange(s,v,NOW+50)
        self.assertEqual(s['commands'][0]['status'],'acknowledged')
    def test_queued_command_cannot_survive_90_seconds_or_session_expiry(self):
        s=self.state();a=command('search_gold')
        r.enqueue(s,a,NOW)
        v=value();v['observation']['at']=NOW+r.QUEUE_TTL
        s,out=r.exchange(s,v,NOW+r.QUEUE_TTL)
        self.assertIsNone(out['command'])
        self.assertEqual(s['commands'][0]['status'],'expired')
        s=self.state()
        s['expiresAt']=NOW+10
        a=command('inspect')
        self.assertEqual(r.enqueue(s,a,NOW)['expiresAt'],NOW+10)
        v=value();v['observation']['at']=NOW+10
        s,out=r.exchange(s,v,NOW+10)
        self.assertIsNone(out['command'])

    def test_session_replacement_and_no_extension(self):
        s=self.state();r.enqueue(s,command(),NOW)
        v=value();v['expiresAt']+=10
        self.assertEqual(r.exchange(s,v,NOW+10)[0]['expiresAt'],NOW+900)
        v['sessionId']='c'*32
        s,out=r.exchange(s,v,NOW+10)
        self.assertIsNone(out['command']);self.assertEqual(s['commands'],[])
        self.assertEqual(r.enqueue(s,command(),NOW+10)['status'],'session-missing')
    def test_bad_observations_rejected(self):
        for change in [dict(expiresAt=NOW+906),dict(sessionId='raw'),dict(active=1)]:
            with self.assertRaises(ValueError):r.exchange({},dict(value(),**change),NOW)
        for change in [dict(at=NOW-61),dict(nodeCount=501),dict(password='secret'),dict(isins=['bad']),dict(draft='x'*8001)]:
            v=value();v['observation'].update(change)
            with self.assertRaises(ValueError):r.exchange({},v,NOW)
    def test_http_device_cannot_schedule_commands(self):
        sent=[];h=Handler({'action':'mcp','name':'bob_phone_command','arguments':command()},headers={'Authorization':'Bearer '+'a'*64})
        http.route(h,'POST','/api/android-remote/exchange',lambda p,remote=False:sent.append((p,remote)) or {})
        self.assertEqual(sent[0][0]['action'],'exchange');self.assertTrue(sent[0][1])
        with self.assertRaises(ValueError):r.exchange({},sent[0][0]['value'],NOW)
        h=Handler(value(),auth=True)
        http.route(h,'POST','/api/android-remote/exchange',lambda *_:self.fail('cookie control'))
        self.assertEqual(h.code,401)
    def test_mcp_requires_new_explicit_scope(self):
        req={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_phone_command','arguments':command()}}
        _,response=bob_mcp.handle(req,lambda:{},lambda:{},remote_phone=True)
        self.assertTrue(response['result']['isError'])
        self.assertIn(r.SCOPE,response['result']['_meta']['mcp/www_authenticate'][0])
        calls=[]
        _,response=bob_mcp.handle(req,lambda:{},remote_phone=True,phone_handler=lambda n,a:calls.append(a) or {'status':'queued'})
        self.assertEqual(len(calls),1);self.assertFalse(response['result']['isError'])
        req['params']['arguments']['action']='tap'
        _,response=bob_mcp.handle(req,lambda:{},remote_phone=True,phone_handler=lambda *_:self.fail('unsafe'))
        self.assertIn('error',response)
        defs=r.definitions();self.assertTrue(defs[0]['annotations']['readOnlyHint']);self.assertFalse(defs[1]['annotations']['readOnlyHint'])

class Database(unittest.TestCase):
    def test_pair_session_deliver_ack_revoke(self):
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('CI PostgreSQL not configured')
        import psycopg
        with psycopg.connect(url) as conn:
            try:
                conn.execute('CREATE SCHEMA remote_'+ID);conn.execute('SET LOCAL search_path TO remote_'+ID)
                t.init(conn);r.init(conn);token='a'*64;digest=t.token_hash(token)
                with patch('android_remote.time.time',return_value=NOW):
                    with self.assertRaises(PermissionError):r.handle(conn,dict(action='exchange',token=token,value=value()))
                    t.handle(conn,dict(action='register',tokenHash=digest))
                    r.handle(conn,dict(action='exchange',token=token,value=value()))
                    a=dict(command(),deviceId=digest[:12])
                    self.assertEqual(r.handle(conn,dict(action='mcp',name='bob_phone_command',arguments=a))['status'],'queued')
                    answer=r.handle(conn,dict(action='exchange',token=token,value=value()))
                    self.assertEqual(answer['command']['requestId'],a['requestId'])
                    status=r.handle(conn,dict(action='mcp',name='bob_phone_status',arguments={}))
                    self.assertNotIn(token,json.dumps(status));self.assertNotIn(digest,json.dumps(status))
                    t.handle(conn,dict(action='revokeAll'))
                    self.assertEqual(r.handle(conn,dict(action='mcp',name='bob_phone_status',arguments={}))['devices'],[])
                    with self.assertRaises(PermissionError):r.handle(conn,dict(action='exchange',token=token,value=value()))
            finally:conn.rollback()
