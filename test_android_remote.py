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
    def test_termux_check_is_bounded_and_not_a_shell(self):
        accepted=r.arguments('bob_phone_command',command('termux_check'))
        self.assertEqual(accepted['action'],'termux_check')
        self.assertNotIn('command',accepted)
        self.assertNotIn('argv',accepted)
        for extras in (dict(text='ls -la'),dict(args=['cat','secret']),
                       dict(commandLine='printenv'),dict(isin=ISIN)):
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                r.arguments('bob_phone_command',dict(command('termux_check'),**extras))
        self.assertIn('termux_check',r.definitions()[1]['inputSchema']
                      ['properties']['action']['enum'])

    def test_account_settings_require_a_delivered_read_and_redacted_enums(self):
        args=r.arguments('bob_phone_command',command('read_account_settings'))
        self.assertEqual(args['action'],'read_account_settings')
        self.assertIn('read_account_settings',r.definitions()[1]['inputSchema']['properties']['action']['enum'])
        s=self.state();a=command('read_account_settings')
        r.enqueue(s,a,NOW)
        v=value();v['observation']['accountSettings']={
            'source':'degiro-app-local-accessibility','capturedAt':NOW,
            'status':'PARTIAL','feeProfile':None,'autoFx':'ON'}
        v['observation']['code']='ACCOUNT_SETTINGS_PARTIAL'
        v['ack']={'requestId':a['requestId'],'code':'ACCOUNT_SETTINGS_PARTIAL'}
        # Queued is not delivered: a device cannot create an unsolicited read.
        with self.assertRaises(ValueError):r.exchange(s,v,NOW)
        s,_=r.exchange(s,value(),NOW)
        self.assertEqual(s['commands'][0]['status'],'delivered')
        accepted,_=r.exchange(s,v,NOW)
        self.assertEqual(accepted['commands'][0]['status'],'acknowledged')
        self.assertEqual(accepted['observation']['accountSettings']['autoFx'],'ON')
        self.assertNotIn('feesCHF',accepted['observation']['accountSettings'])
        self.assertEqual(accepted['accountSettings']['autoFx'],'ON')
        self.assertFalse(accepted['accountSettings']['accountFeeConfirmed'])
        self.assertFalse(accepted['accountSettings']['brokerExecutionConfirmed'])
        # Later product heartbeats may not erase the consented settings receipt.
        after,_=r.exchange(accepted,value(),NOW+1)
        self.assertEqual(after['accountSettings']['capturedAt'],NOW)
        # Network retries remain idempotent after a lost response.
        r.exchange(accepted,v,NOW)
        for bad in (
            {'feeProfile':'basic'}, {'autoFx':'AUTO_CHF'}, {'feesCHF':0},
            {'source':'untrusted'}, {'status':'COMPLETE'}, {'capturedAt':NOW-61},
            {'accountNumber':'secret'}):
            wrong=value();wrong['observation']['code']='ACCOUNT_SETTINGS_PARTIAL'
            wrong['observation']['accountSettings']={**v['observation']['accountSettings'],**bad}
            wrong['ack']=v['ack']
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                r.exchange(accepted,wrong,NOW)
        wrong=value();wrong['observation']['accountSettings']=v['observation']['accountSettings']
        wrong['observation']['code']='ACCOUNT_SETTINGS_PARTIAL'
        wrong['ack']={'requestId':'c'*32,'code':'ACCOUNT_SETTINGS_PARTIAL'}
        with self.assertRaises(ValueError):r.exchange(accepted,wrong,NOW)

    def test_local_owner_settings_receipt_without_stale_connector_command(self):
        # Current ChatGPT connector still exposes product actions only. The
        # dedicated on-device settings button grants one scoped, local read.
        s0=self.state()
        owner=value();owner['purpose']='owner_account_settings'
        s,response=r.exchange({},owner,NOW)
        self.assertEqual(s['purpose'],'owner_account_settings')
        self.assertIsNone(response['command'])
        v=copy.deepcopy(owner)
        v['observation'].update(code='ACCOUNT_SETTINGS_PARTIAL',
                                accountSettings=dict(
                                    source='degiro-app-local-accessibility',
                                    capturedAt=NOW,status='PARTIAL',
                                    feeProfile=None,autoFx='ON'))
        saved,_=r.exchange(s,v,NOW)
        self.assertEqual(saved['accountSettings']['autoFx'],'ON')
        self.assertIsNone(saved['accountSettings']['feeProfile'])
        self.assertFalse(saved['accountSettings']['accountFeeConfirmed'])
        self.assertFalse(saved['accountSettings']['brokerExecutionConfirmed'])
        self.assertEqual(saved['commands'],[])
        # Safe duplicate after a network retry; a changed receipt is not.
        r.exchange(saved,v,NOW)
        altered=copy.deepcopy(v)
        altered['observation']['accountSettings']['autoFx']='OFF'
        with self.assertRaises(ValueError):r.exchange(saved,altered,NOW)
        altered=copy.deepcopy(v)
        altered['observation']['accountSettings']['accountNumber']='secret'
        with self.assertRaises(ValueError):r.exchange(saved,altered,NOW)
        altered=copy.deepcopy(v)
        altered['observation']['isins']=['DE000FE2JJ20']
        with self.assertRaises(ValueError):r.exchange(saved,altered,NOW)
        # Session purpose can never be escalated after starting a product read.
        with self.assertRaises(ValueError):r.exchange(s0,owner,NOW)
        with self.assertRaises(ValueError):r.exchange(saved,value(),NOW)
        # A product-only heartbeat cannot invent a valid owner receipt.
        normal=copy.deepcopy(v)
        normal['purpose']='product_read'
        with self.assertRaises(ValueError):r.exchange(s0,normal,NOW)
        # Inactive session is not permission to send further account data.
        stopped=copy.deepcopy(v);stopped['active']=False
        with self.assertRaises(ValueError):r.exchange(s,stopped,NOW)
        # No unrecognized session purposes, extra keys or fake ack.
        wrong=copy.deepcopy(owner);wrong['purpose']='broker_orders'
        with self.assertRaises(ValueError):r.exchange({},wrong,NOW)
        wrong=copy.deepcopy(owner);wrong['credentials']='secret'
        with self.assertRaises(ValueError):r.exchange({},wrong,NOW)
        wrong=copy.deepcopy(v);wrong['ack']={'requestId':'c'*32,
                                          'code':'ACCOUNT_SETTINGS_PARTIAL'}
        with self.assertRaises(ValueError):r.exchange(s,wrong,NOW)
        # Receipt remains visible through subsequent safe heartbeat.
        after,_=r.exchange(saved,owner,NOW+1)
        self.assertEqual(after['accountSettings']['autoFx'],'ON')

    def test_basic_owner_confirmation_is_not_an_executed_fee_or_remote_command(self):
        owner=value()
        owner['purpose']='owner_account_settings'
        state,_=r.exchange({},owner,NOW)
        receipt=copy.deepcopy(owner)
        receipt['observation'].update(code='ACCOUNT_SETTINGS_PARTIAL',
             accountSettings={'source':'degiro-app-owner-confirmed',
                 'capturedAt':NOW,'status':'PARTIAL',
                 'feeProfile':'BASIC','autoFx':None})
        saved,_=r.exchange(state,receipt,NOW)
        self.assertEqual(saved['verifiedSettings']['feeProfile']['value'],'BASIC')
        self.assertEqual(saved['verifiedSettings']['feeProfile']['source'],
                         'degiro-app-owner-confirmed')
        self.assertFalse(saved['accountSettings']['accountFeeConfirmed'])
        self.assertFalse(saved['accountSettings']['brokerExecutionConfirmed'])
        self.assertFalse(saved['sameAccountAcrossSessionsConfirmed'])
        self.assertEqual(saved['commands'],[])
        r.exchange(saved,receipt,NOW)  # retry, unchanged
        altered=copy.deepcopy(receipt)
        altered['observation']['accountSettings']['autoFx']='ON'
        altered['observation']['accountSettings']['status']='COMPLETE'
        altered['observation']['code']='ACCOUNT_SETTINGS_COMPLETE'
        with self.assertRaises(ValueError):r.exchange(saved,altered,NOW)
        altered=copy.deepcopy(receipt)
        altered['observation']['accountSettings']['feeProfile']='TRADER'
        with self.assertRaises(ValueError):r.exchange(saved,altered,NOW)
        altered=copy.deepcopy(receipt)
        altered['purpose']='product_read'
        with self.assertRaises(ValueError):r.exchange(saved,altered,NOW)
        # The remote MCP command cannot impersonate a local owner assertion.
        a=command('read_account_settings');r.enqueue(state,a,NOW)
        state,_=r.exchange(state,owner,NOW)
        altered=copy.deepcopy(receipt)
        altered['ack']={'requestId':a['requestId'],'code':'ACCOUNT_SETTINGS_PARTIAL'}
        altered['purpose']='product_read'
        with self.assertRaises(ValueError):r.exchange(state,altered,NOW)

    def test_basic_and_autofx_evidence_survive_separate_bounded_sessions(self):
        owner=value();owner['purpose']='owner_account_settings'
        state,_=r.exchange({},owner,NOW)
        basic=copy.deepcopy(owner)
        basic['observation'].update(code='ACCOUNT_SETTINGS_PARTIAL',
            accountSettings={'source':'degiro-app-owner-confirmed',
                'capturedAt':NOW,'status':'PARTIAL',
                'feeProfile':'BASIC','autoFx':None})
        state,_=r.exchange(state,basic,NOW)
        # New owner-started session: retain verified enums, not session grant.
        next_value=value();next_value['purpose']='owner_account_settings'
        next_value['sessionId']='c'*32
        next_value['expiresAt']=NOW+920
        next_value['observation']['at']=NOW+20
        state,_=r.exchange(state,next_value,NOW+20)
        self.assertEqual(state['commands'],[])
        self.assertEqual(state['verifiedSettings']['feeProfile']['value'],'BASIC')
        self.assertNotIn('accountSettings',state)
        fx=copy.deepcopy(next_value)
        fx['observation'].update(code='ACCOUNT_SETTINGS_PARTIAL',
            accountSettings={'source':'degiro-app-local-accessibility',
                'capturedAt':NOW+20,'status':'PARTIAL',
                'feeProfile':None,'autoFx':'ON'})
        state,_=r.exchange(state,fx,NOW+20)
        self.assertEqual(state['verifiedSettings']['autoFx']['value'],'ON')
        self.assertEqual(state['verifiedSettings']['feeProfile']['value'],'BASIC')
        self.assertFalse(state['sameAccountAcrossSessionsConfirmed'])
        # Neither evidence can be silently upgraded into a fee/FX trade approval.
        self.assertFalse(state['accountSettings']['accountFeeConfirmed'])
        self.assertFalse(state['accountSettings']['brokerExecutionConfirmed'])
        # Ageing out discards old settings; do not keep permanent cross-account
        # state after the user might have switched DEGIRO accounts.
        later=copy.deepcopy(next_value)
        later['sessionId']='d'*32
        far=NOW+r.ACCOUNT_EVIDENCE_MAX_AGE+5
        later['expiresAt']=far+900
        later['observation']['at']=far
        state,_=r.exchange(state,later,far)
        self.assertEqual(state['verifiedSettings'],{})

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
