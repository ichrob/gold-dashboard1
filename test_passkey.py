"""Verify actual WebAuthn signatures and Bob's second-factor boundaries offline."""
import base64
import hashlib
import json
import os
import unittest
from unittest.mock import patch
import cbor2
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
import bob_passkey_store as store
import bob_passkey
import bob_auth

class PasskeyTests(unittest.TestCase):
    def setUp(self):
        self.state={}
        self.payload={'account':'a'*64,'binding':'b'*64}
        self.key=ec.generate_private_key(ec.SECP256R1())
        self.cid=b'credential-test-id'
        n=self.key.public_key().public_numbers()
        self.cose=cbor2.dumps({1:2,3:-7,-1:1,-2:n.x.to_bytes(32,'big'),-3:n.y.to_bytes(32,'big')})

    def call(self,action,now=100,**fields):
        return store.transition(self.state,action,{**self.payload,**fields},now)

    def credential(self,options,register=False,origin=store.ORIGIN,uv=True,challenge=None,key=None):
        client=json.dumps({'type':'webauthn.create' if register else 'webauthn.get','challenge':challenge or options['challenge'],'origin':origin}).encode()
        flags=1+(4 if uv else 0)+(64 if register else 0)
        auth=hashlib.sha256(store.RP_ID.encode()).digest()+bytes([flags])+(0 if register else 1).to_bytes(4,'big')
        if register:
            auth+=bytes(16)+len(self.cid).to_bytes(2,'big')+self.cid+self.cose
            response={'attestationObject':store.encode(cbor2.dumps({'fmt':'none','attStmt':{},'authData':auth}))}
        else:
            response={'authenticatorData':store.encode(auth),'signature':store.encode((key or self.key).sign(auth+hashlib.sha256(client).digest(),ec.ECDSA(hashes.SHA256())))}
        response['clientDataJSON']=store.encode(client)
        return {'id':store.encode(self.cid),'rawId':store.encode(self.cid),'type':'public-key','response':response}

    def enroll(self):
        opts=self.call('register-options')['options']
        result=self.call('register-verify',credential=self.credential(opts,True))
        self.assertTrue(result['ok'],result)
        return result

    def test_real_registration_and_daily_expiry_not_sliding(self):
        result=self.enroll()
        self.assertEqual(len(result['recoveryCodes']),8)
        self.assertNotIn(result['recoveryCodes'][0],json.dumps(self.state))
        self.assertTrue(self.call('status',now=100+store.TTL-1)['verified'])
        self.assertFalse(self.call('status',now=100+store.TTL)['verified'])
        options=self.call('authenticate-options',now=100+store.TTL)['options']
        verified=self.call('authenticate-verify',now=100+store.TTL,credential=self.credential(options))
        self.assertTrue(verified['ok'])
        self.assertEqual(verified['validUntil'],100+2*store.TTL)

    def test_registration_rejects_wrong_origin_challenge_and_no_uv(self):
        for kwargs in ({'origin':'https://evil.invalid'},{'challenge':store.encode(b'wrong')},{'uv':False}):
            with self.subTest(kwargs=kwargs):
                self.state={}
                options=self.call('register-options')['options']
                self.assertFalse(self.call('register-verify',credential=self.credential(options,True,**kwargs))['ok'])
                self.assertFalse(self.call('status')['enabled'])

    def test_authentication_rejects_bad_signature_and_replay(self):
        self.enroll()
        options=self.call('authenticate-options')['options']
        bad=self.credential(options,key=ec.generate_private_key(ec.SECP256R1()))
        self.assertFalse(self.call('authenticate-verify',credential=bad)['ok'])
        self.assertFalse(self.call('authenticate-verify',credential=self.credential(options))['ok'])
        options=self.call('authenticate-options')['options']
        good=self.credential(options)
        self.assertTrue(self.call('authenticate-verify',credential=good)['ok'])
        self.assertFalse(self.call('authenticate-verify',credential=good)['ok'])

    def test_new_session_cannot_enroll_without_second_factor(self):
        self.enroll()
        self.payload['binding']='c'*64
        self.assertFalse(self.call('status')['verified'])
        self.assertEqual(self.call('register-options')['error'],'PASSKEY_REQUIRED')

    def test_recovery_one_use_bound_to_session_and_retains_factor(self):
        code=self.enroll()['recoveryCodes'][0]
        self.payload['binding']='c'*64
        self.assertTrue(self.call('recover',code=code)['ok'])
        self.assertTrue(self.call('status')['verified'])
        self.assertTrue(self.call('status')['enabled'])
        self.payload['binding']='d'*64
        self.assertFalse(self.call('recover',code=code)['ok'])
        self.assertFalse(self.call('status')['verified'])

    def test_expired_challenge_and_failure_throttle(self):
        options=self.call('register-options')['options']
        self.assertFalse(self.call('register-verify',now=400,credential=self.credential(options,True))['ok'])
        for _ in range(4):self.call('recover',now=400,code='wrong')
        self.assertEqual(self.call('register-options',now=401)['error'],'TOO_MANY_ATTEMPTS')
        self.assertTrue(self.call('register-options',now=701)['ok'])

    def test_remove_lost_key_clears_other_proofs_and_cannot_remove_last(self):
        self.enroll()
        old=store.encode(self.cid)
        self.state['credentials']['other']={'key':'unused','count':0}
        self.state['proofs']['c'*64]=100+store.TTL
        self.state['proofKeys']['c'*64]='other'
        self.assertTrue(self.call('revoke-credential',credentialId='other')['ok'])
        self.assertNotIn('c'*64,self.state['proofs'])
        self.assertTrue(self.call('status')['verified'])
        self.assertEqual(self.call('revoke-credential',credentialId=old)['error'],'LAST_CREDENTIAL')

    def test_recovery_rotation_only_replaces_old_codes_after_confirmation(self):
        codes=self.enroll()['recoveryCodes']
        self.assertTrue(self.call('confirm-recovery',code=codes[0])['ok'])
        old=list(self.state['recovery'])
        new=self.call('rotate-recovery')['recoveryCodes']
        self.assertEqual(self.state['recovery'],old)
        self.assertFalse(self.call('confirm-recovery',code='bad')['ok'])
        self.assertEqual(self.state['recovery'],old)
        self.assertTrue(self.call('confirm-recovery',code=new[0])['ok'])
        self.assertNotEqual(self.state['recovery'],old)
        self.assertFalse(self.call('recover',code=codes[0])['ok'])
        self.assertTrue(self.call('recover',code=new[0])['ok'])

    def test_sensitive_management_needs_recent_second_factor(self):
        self.enroll()
        for action in ('rotate-recovery','machine-authorize','revoke-credential'):
            self.assertEqual(self.call(action,now=401)['error'],'FRESH_PASSKEY_REQUIRED')
        self.payload['binding']='d'*64
        self.assertEqual(self.call('machine-authorize')['error'],'PASSKEY_REQUIRED')

    def test_machine_setup_before_enrollment_and_recovery_then_new_key(self):
        self.assertTrue(self.call('machine-authorize')['ok'])
        code=self.enroll()['recoveryCodes'][0]
        old=store.encode(self.cid)
        self.payload['binding']='c'*64
        self.assertTrue(self.call('recover',code=code)['ok'])
        self.cid=b'replacement-key'
        self.enroll()
        self.assertTrue(self.call('revoke-credential',credentialId=old)['ok'])
        self.assertNotIn(old,self.state['credentials'])
        self.assertNotIn('b'*64,self.state['proofs'])

    def test_gate_off_does_not_call_store(self):
        with patch.dict(os.environ,{'BOB_PASSKEY_AVAILABLE':'0'}),patch.object(bob_passkey,'rpc') as rpc:
            bob_passkey.require({},'user','pw')
            rpc.assert_not_called()

    def test_basic_cannot_substitute_for_valid_cookie(self):
        headers={'Authorization':'Basic abc','Cookie':bob_auth.COOKIE+'=forged'}
        def validate(h,*args):
            self.assertNotIn('Authorization',h)
            return False
        with patch.dict(os.environ,{'BOB_PASSKEY_AVAILABLE':'1'}),patch.object(bob_passkey,'rpc',return_value={'enabled':True,'verified':True}),patch.object(bob_auth,'primary_authenticated',side_effect=validate):
            with self.assertRaises(bob_passkey.PasskeyRequired):bob_passkey.require(headers,'user','pw')

    def test_storage_failure_denies_access(self):
        with patch.dict(os.environ,{'BOB_PASSKEY_AVAILABLE':'1'}),patch.object(bob_passkey,'rpc',side_effect=OSError):
            with self.assertRaises(bob_auth.AuthenticationUnavailable):bob_passkey.require({},'user','pw')


class PasskeyHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server,threading
        cls.server=server
        cls.previous=(server.USER,server.PASSWORD)
        server.USER,server.PASSWORD='passkey-test','test-password'
        cls.httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join()
        cls.server.USER,cls.server.PASSWORD=cls.previous
    def setUp(self):
        import time
        bob_auth.FAILURES.clear()
        bob_auth.SESSIONS['test-session']=(time.time()+600,0)
        self.env=patch.dict(os.environ,{'BOB_PASSKEY_AVAILABLE':'1'})
        self.env.start();self.addCleanup(self.env.stop)
        self.recovery=patch.object(bob_auth.bob_recovery,'state',return_value={'version':0})
        self.recovery.start();self.addCleanup(self.recovery.stop)
    def request(self,method,path,headers=None,body=None):
        import http.client
        conn=http.client.HTTPConnection('127.0.0.1',self.httpd.server_port)
        base={'Host':'bob.example','Cookie':bob_auth.COOKIE+'=test-session'}
        base.update(headers or {})
        conn.request(method,path,body,base)
        r=conn.getresponse();out=(r.status,dict(r.getheaders()),r.read());conn.close();return out
    def test_unverified_session_redirects_page_but_api_denied(self):
        with patch.object(bob_passkey,'rpc',return_value={'enabled':True,'verified':False}):
            status,h,_=self.request('GET','/')
            self.assertEqual(status,303);self.assertEqual(h['Location'],'/passkey')
            self.assertEqual(self.request('GET','/api/live')[0],403)
            self.assertEqual(self.request('GET','/passkey')[0],200)
    def test_verified_session_loads_app(self):
        with patch.object(bob_passkey,'rpc',return_value={'enabled':True,'verified':True}):
            self.assertEqual(self.request('GET','/')[0],200)
    def test_cross_origin_and_basic_only_setup_rejected(self):
        with patch.object(bob_passkey,'rpc') as rpc:
            self.assertEqual(self.request('POST','/api/passkey/register-options',{'Origin':'https://evil.invalid','Content-Type':'application/json'},'{}')[0],403)
            self.assertEqual(self.request('GET','/passkey',{'Cookie':'','Authorization':'Basic '+base64.b64encode(b'passkey-test:test-password').decode()})[0],303)
            rpc.assert_not_called()

    def test_mcp_machine_token_is_scoped_and_survives_daily_factor(self):
        token='test-only-machine-token-not-a-secret-123456789'
        headers={'Cookie':'','Authorization':'Bearer '+token,'Content-Type':'application/json'}
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/list'})
        with patch.dict(os.environ,{'BOB_MCP_SERVICE_TOKEN':token}),patch.object(bob_passkey,'rpc',return_value={'enabled':True,'verified':False}):
            response=self.request('POST','/mcp',headers,body)
            self.assertEqual(response[0],200)
            self.assertEqual({t['name'] for t in json.loads(response[2])['result']['tools']},{'bob_product_audit','bob_product_gaps','bob_diagnostics','bob_signal_history','bob_push_history','bob_push_devices','bob_push_test','bob_push_test_status','bob_phone_status','bob_phone_command'})
            test_body=json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'bob_push_test','arguments':{'deviceId':'device-1','requestId':'a'*32}}})
            with patch.object(self.server,'remote_push_rpc') as sender:
                denied=json.loads(self.request('POST','/mcp',headers,test_body)[2])['result']
                self.assertTrue(denied['isError'])
                self.assertIn('bob:push:test',denied['_meta']['mcp/www_authenticate'][0])
                sender.assert_not_called()
            phone_body=json.dumps({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'bob_phone_command','arguments':{'deviceId':'a'*12,'sessionId':'b'*32,'requestId':'c'*32,'action':'search_gold'}}})
            with patch.object(self.server,'android_diagnostic_rpc') as sender:
                denied=json.loads(self.request('POST','/mcp',headers,phone_body)[2])['result']
                self.assertTrue(denied['isError'])
                self.assertIn('bob:phone:control',denied['_meta']['mcp/www_authenticate'][0])
                sender.assert_not_called()
            diagnostic_body=json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'bob_diagnostics'}})
            with patch.object(self.server,'read_diagnostics_for_mcp') as reader:
                result=json.loads(self.request('POST','/mcp',headers,diagnostic_body)[2])['result']
                self.assertTrue(result['isError'])
                self.assertIn('insufficient_scope',result['_meta']['mcp/www_authenticate'][0])
                reader.assert_not_called()
            self.assertEqual(self.request('GET','/api/live',headers)[0],401)
            self.assertEqual(self.request('GET','/passkey',headers)[0],303)
            self.assertEqual(self.request('POST','/api/real-trades/write',headers,'{}')[0],401)
            machine_basic={**headers,'Authorization':'Basic '+base64.b64encode(('bob-readonly:'+token).encode()).decode()}
            self.assertEqual(self.request('POST','/mcp',machine_basic,body)[0],200)
            self.assertEqual(self.request('GET','/api/live',machine_basic)[0],401)
            bad={**headers,'Authorization':'Bearer wrong'}
            self.assertEqual(self.request('POST','/mcp',bad,body)[0],401)
            basic={**headers,'Authorization':'Basic '+base64.b64encode(b'passkey-test:test-password').decode()}
            self.assertEqual(self.request('POST','/mcp',basic,body)[0],403)
        with patch.dict(os.environ,{'BOB_MCP_SERVICE_TOKEN':''}):
            self.assertEqual(self.request('POST','/mcp',headers,body)[0],401)

if __name__=='__main__':unittest.main()
