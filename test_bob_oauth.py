"""OAuth security boundaries: actual HTTP routes and deterministic state tests."""
import copy
import http.client
import json
import re
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlparse, parse_qs
import bob_oauth as oauth
import bob_oauth_store as store
import bob_auth
import server


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.now = 100
        self.cid = self.call('register',redirect_uris=[store.REDIRECT])['client_id']
        self.verifier = 'v'*43

    def call(self, action, **p):
        return store.transition(self.state,action,p,self.now)

    def begin(self, **overrides):
        return self.call('begin',**dict(client_id=self.cid,redirect_uri=store.REDIRECT,
            response_type='code',scope=store.SCOPE,resource=store.RESOURCE,state='test-state',
            code_challenge=store.challenge(self.verifier),code_challenge_method='S256',**{} ) | overrides)

    def authorize(self):
        req = self.begin()['request']
        return self.call('approve',request=req,until=self.now+10000)['code']

    def exchange(self, code, **overrides):
        fields = dict(client_id=self.cid,redirect_uri=store.REDIRECT,grant_type='authorization_code',
                      code=code,code_verifier=self.verifier,resource=store.RESOURCE)
        fields.update(overrides)
        return self.call('token',**fields)

    def refresh(self, token, **overrides):
        fields = dict(client_id=self.cid,grant_type='refresh_token',refresh_token=token,resource=store.RESOURCE)
        fields.update(overrides)
        return self.call('token',**fields)

    def test_pkce_resource_scope_client_and_redirect_enforced(self):
        for field,value in [('redirect_uri','https://evil.example/callback'),('resource','https://other.example'),
                            ('scope','write'),('code_challenge_method','plain'),('client_id','unknown'),
                            ('response_type','token'),('code_challenge','short'),('state','')]:
            self.assertIn('error',self.begin(**{field:value}))
        code = self.authorize()
        for field,value in [('redirect_uri','https://evil.example'),('resource','other'),('scope','write'),
                            ('client_id','unknown'),('code_verifier','x'*43)]:
            self.assertIn('error',self.exchange(code,**{field:value}))
        tokens = self.exchange(code)
        self.assertTrue(self.call('check',token=tokens['access_token'])['valid'])
        self.assertFalse(self.call('check',token=tokens['refresh_token'])['valid'])
        self.assertFalse(self.call('check',token=code)['valid'])
        self.assertNotIn(tokens['access_token'],json.dumps(self.state))
        self.assertNotIn(tokens['refresh_token'],json.dumps(self.state))

    def test_push_test_scope_requires_new_explicit_consent(self):
        tokens=self.exchange(self.authorize())
        self.assertNotIn(store.PUSH_TEST_SCOPE,self.call('check',token=tokens['access_token'])['scope'])
        self.assertEqual(self.refresh(tokens['refresh_token'],scope=store.PUSH_TEST_SCOPE)['error'],'invalid_scope')
        req=self.begin(scope=store.DIAGNOSTICS_SCOPE+' '+store.PUSH_TEST_SCOPE)['request']
        self.assertIn(store.PUSH_TEST_SCOPE,self.call('pending',request=req)['scope'])
        code=self.call('approve',request=req,until=self.now+10000)['code']
        new=self.exchange(code)
        self.assertIn(store.PUSH_TEST_SCOPE,self.call('check',token=new['access_token'])['scope'])
        self.assertNotIn(store.PUSH_TEST_SCOPE,self.call('check',token=tokens['access_token'])['scope'])

    def test_code_replay_revokes_grant(self):
        code = self.authorize()
        tokens = self.exchange(code)
        self.assertIn('error',self.exchange(code))
        self.assertFalse(self.call('check',token=tokens['access_token'])['valid'])

    def test_refresh_rotation_reuse_and_audience(self):
        tokens = self.exchange(self.authorize())
        self.assertIn('error',self.refresh(tokens['refresh_token'],resource='other'))
        new = self.refresh(tokens['refresh_token'])
        self.assertNotEqual(tokens['refresh_token'],new['refresh_token'])
        self.assertTrue(self.call('check',token=new['access_token'])['valid'])
        self.assertIn('error',self.refresh(tokens['refresh_token']))
        self.assertFalse(self.call('check',token=new['access_token'])['valid'])

    def test_expiry_survives_serialization_and_no_automatic_extension(self):
        tokens = self.exchange(self.authorize())
        self.state = json.loads(json.dumps(self.state))
        self.assertTrue(self.call('check',token=tokens['access_token'])['valid'])
        self.now += store.ACCESS_TTL
        self.assertFalse(self.call('check',token=tokens['access_token'])['valid'])
        new = self.refresh(tokens['refresh_token'])
        self.now = 10100
        self.assertIn('error',self.refresh(new['refresh_token']))
        self.assertFalse(self.call('check',token=new['access_token'])['valid'])

    def test_denial_expired_pending_and_grant_limit(self):
        req = self.begin()['request']
        denied = self.call('deny',request=req)
        self.assertEqual(denied['iss'],store.ORIGIN)
        self.assertEqual(denied['state'],'test-state')
        self.assertNotIn('code',denied)
        self.assertIn('error',self.call('approve',request=req,until=200))
        req = self.begin()['request']
        self.now += 901
        self.assertIn('error',self.call('pending',request=req))

    def test_registration_cannot_inject_redirect_or_create_unbounded_clients(self):
        for uri in ['http://chatgpt.com/connector_platform_oauth_redirect',store.REDIRECT+'?next=evil',
                    'https://chatgpt.com.evil.example/callback','https://evil.example']:
            self.assertIn('error',self.call('register',redirect_uris=[uri]))
        for _ in range(200):
            self.assertEqual(self.cid,self.call('register',redirect_uris=[store.REDIRECT])['client_id'])
        self.assertEqual(len(self.state['clients']),1)

    def test_revocation(self):
        tokens = self.exchange(self.authorize())
        self.call('revoke',token=tokens['refresh_token'],client_id='wrong')
        self.assertTrue(self.call('check',token=tokens['access_token'])['valid'])
        self.call('revoke',token=tokens['refresh_token'],client_id=self.cid)
        self.assertFalse(self.call('check',token=tokens['access_token'])['valid'])
        tokens = self.exchange(self.authorize())
        self.call('revoke-all')
        self.assertFalse(self.call('check',token=tokens['access_token'])['valid'])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.lock = threading.Lock()
        def rpc(action,user,**fields):
            with self.lock:
                return store.transition(self.state,action,fields)
        self.patchers = [patch.object(oauth,'rpc',side_effect=rpc),patch.object(oauth,'configured',return_value=True),
            patch.object(server,'USER','test-user'),patch.object(server,'PASSWORD','test-only-password'),
            patch('bob_recovery.state',return_value={'passwordHash':None,'version':0}),
            patch('bob_passkey.enabled',return_value=False)]
        for p in self.patchers:p.start()
        bob_auth.SESSIONS['test-session'] = (time.time()+600,0)
        self.httpd = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.thread.start()
        self.session = bob_auth.COOKIE+'=test-session'

    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.thread.join()
        for p in reversed(self.patchers):p.stop()
        bob_auth.SESSIONS.clear()

    def request(self,method,path,body=None,headers=None):
        conn = http.client.HTTPConnection('127.0.0.1',self.httpd.server_port,timeout=5)
        conn.request(method,path,body,headers or {})
        response = conn.getresponse()
        result = response.status,dict(response.getheaders()),response.read()
        conn.close()
        return result

    def form(self,path,fields,cookie='',origin=store.ORIGIN):
        return self.request('POST',path,urlencode(fields),{'Content-Type':'application/x-www-form-urlencoded',
            'Origin':origin,'Cookie':cookie})

    def begin(self):
        status,_,body = self.request('POST','/oauth/register',json.dumps({'redirect_uris':[store.REDIRECT]}),{'Content-Type':'application/json'})
        self.assertEqual(status,201)
        self.cid = json.loads(body)['client_id']
        self.verifier = 'v'*43
        params = dict(client_id=self.cid,redirect_uri=store.REDIRECT,response_type='code',scope=store.SCOPE,
            resource=store.RESOURCE,state='state',code_challenge=store.challenge(self.verifier),code_challenge_method='S256')
        status,h,_ = self.request('GET','/oauth/authorize?'+urlencode(params))
        self.assertEqual(status,303)
        self.cookie = h['Set-Cookie'].split(';')[0]
        self.nonce = self.cookie.split('=',1)[1]

    def test_discovery_and_no_anonymous_report(self):
        status,_,body = self.request('GET','/.well-known/oauth-authorization-server')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['code_challenge_methods_supported'],['S256'])
        status,h,_ = self.request('POST','/mcp','{}',{'Content-Type':'application/json'})
        self.assertEqual(status,401)
        self.assertIn('resource_metadata=',h['WWW-Authenticate'])
        self.assertTrue(h['WWW-Authenticate'].startswith('Bearer '))
        for path,expected in [('/',303),('/api/degiro/audit',401)]:
            status,h,_ = self.request('GET',path)
            self.assertEqual(status,expected)
            self.assertNotIn('WWW-Authenticate',h)

    def test_actual_consent_and_read_only_mcp_flow(self):
        self.begin()
        status,h,_ = self.request('GET','/oauth/resume',headers={'Cookie':self.cookie})
        self.assertEqual((status,h['Location']),(303,'/login'))
        cookies = self.cookie+'; '+self.session
        status,h,body = self.request('GET','/oauth/resume',headers={'Cookie':cookies})
        self.assertEqual(status,200)
        # HTML form POSTs get Origin: null under no-referrer, breaking consent.
        self.assertEqual(h['Referrer-Policy'],'same-origin')
        # Chrome also applies form-action to the post-consent redirect.
        self.assertIn("form-action 'self' "+store.REDIRECT+";",h['Content-Security-Policy'])
        self.assertIn(b'Lesezugriff erlauben',body)
        fields = {'request':self.nonce,'decision':'approve'}
        self.assertEqual(self.form('/oauth/consent',fields,cookies,origin='https://evil.example')[0],403)
        self.assertEqual(self.form('/oauth/consent',fields,cookies,origin='null')[0],403)
        self.assertEqual(self.form('/oauth/consent',fields,cookies,origin='')[0],403)
        self.assertEqual(self.form('/oauth/consent',{**fields,'request':'wrong'},cookies)[0],403)
        status,h,body = self.form('/oauth/consent',fields,cookies)
        self.assertEqual(status,200)
        self.assertNotIn('Location',h)
        self.assertEqual(h['Cache-Control'],'no-store')
        self.assertIn('Max-Age=0',h['Set-Cookie'])
        self.assertIn(b'referrerpolicy="no-referrer"',body)
        self.assertNotIn(b'<form',body)
        import re,html
        destination=html.unescape(re.search(r'href="([^"]+)"',body.decode()).group(1))
        self.assertEqual(destination.split('?')[0],store.REDIRECT)
        result = parse_qs(urlparse(destination).query)
        # A replay must not create a second authorization grant.
        self.assertEqual(self.form('/oauth/consent',fields,cookies)[0],400)
        self.assertEqual(result['iss'],[store.ORIGIN])
        status,_,body = self.form('/oauth/token',dict(grant_type='authorization_code',client_id=self.cid,
            redirect_uri=store.REDIRECT,code=result['code'][0],code_verifier=self.verifier,resource=store.RESOURCE))
        self.assertEqual(status,200)
        token = json.loads(body)['access_token']
        headers = {'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        with patch.object(server,'read_private_product_audit_for_mcp',return_value={'status':'ok','items':[]}) as reader:
            payload = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'bob_product_gaps','arguments':{}}}
            self.assertEqual(self.request('POST','/mcp',json.dumps(payload),headers)[0],200)
            self.assertEqual(reader.call_count,1)
            payload['params']['name'] = 'place_order'
            self.assertIn('error',json.loads(self.request('POST','/mcp',json.dumps(payload),headers)[2]))
            self.assertEqual(reader.call_count,1)
        self.assertEqual(self.request('GET','/api/degiro/audit',headers=headers)[0],401)
        self.assertEqual(self.form('/oauth/disconnect',{'csrf':'wrong'},cookies)[0],403)
        self.assertEqual(self.form('/oauth/disconnect',{'csrf':oauth.csrf({'Cookie':self.session})},cookies)[0],303)
        self.assertEqual(self.request('POST','/mcp','{}',headers)[0],401)

    def test_daily_factor_cannot_be_bypassed(self):
        self.begin()
        with patch('bob_passkey.require',side_effect=server.bob_passkey.PasskeyRequired()):
            status,h,_ = self.form('/oauth/consent',{'request':self.nonce,'decision':'approve'},self.cookie+'; '+self.session)
            self.assertEqual((status,h['Location']),(303,'/passkey?oauth=1'))
        self.assertFalse(self.state['grants'])

    def test_store_outage_and_malformed_requests_fail_closed(self):
        with patch.object(oauth,'rpc',side_effect=OSError()):
            self.assertEqual(self.request('POST','/mcp','{}',{'Content-Type':'application/json','Authorization':'Bearer boa_'+'a'*43})[0],503)
        self.assertEqual(self.form('/oauth/token',{'client_id':'unknown','grant_type':'password'})[0],400)
        status,_,_ = self.request('POST','/oauth/token','client_id=a&client_id=b',{'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(status,400)


if __name__=='__main__':
    unittest.main()
