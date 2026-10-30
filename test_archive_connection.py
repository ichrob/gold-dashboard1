import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import archive_connection as c
import archive_connect_web as w

CONFIG={'web':{'client_id':'1234567890-test.apps.googleusercontent.com','client_secret':'test-secret-123456789',
               'token_uri':'https://evil.example','redirect_uris':['https://evil.example']}}
BINDING='a'*64

class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.state={}
        self.call('configure',config=CONFIG)
    def call(self, action, **fields):
        return c.transition(self.state,action,dict(binding=BINDING,**fields),now=100)
    def begin(self):
        return parse_qs(urlparse(self.call('begin')['url']).query)
    def test_upload_discards_urls_and_no_secret_reply(self):
        self.assertEqual(set(self.state['client']),{'client_id','client_secret'})
        self.assertNotIn('test-secret',json.dumps(self.call('status')))
        for config in ({'installed':CONFIG['web']},{'web':{'client_id':'bad','client_secret':'x'*30}}):
            with self.assertRaises(ValueError):self.call('configure',config=config)
    def test_narrow_scope_pkce_offline_fixed_callback(self):
        q=self.begin()
        self.assertEqual(q['scope'],[c.SCOPE]);self.assertEqual(q['redirect_uri'],[c.CALLBACK])
        self.assertEqual(q['code_challenge_method'],['S256']);self.assertEqual(q['access_type'],['offline'])
        self.assertNotIn('client_secret',q)
        self.assertNotIn(q['state'][0],json.dumps(self.state))
    def test_session_expiry_state_and_replay(self):
        nonce=self.begin()['state'][0]
        for binding,state,now in [('b'*64,nonce,100),(BINDING,'x'*43,100),(BINDING,nonce,701)]:
            with self.assertRaises(ValueError):c.transition(self.state,'complete',dict(binding=binding,state=state),now=now)
        self.call('complete',state=nonce)
        with self.assertRaises(ValueError):self.call('complete',state=nonce)
    def test_replacing_client_invalidates_pending(self):
        nonce=self.begin()['state'][0]
        self.call('configure',config=CONFIG)
        with self.assertRaises(ValueError):self.call('complete',state=nonce)
    def test_connected_client_not_silently_replaced(self):
        self.state['credentials']={'refresh_token':'private'}
        with self.assertRaises(ValueError):self.call('configure',config=CONFIG)
        self.assertFalse(self.call('status')['archiveEnabled'])
    def test_encryption_and_key_separation(self):
        with patch.dict('os.environ',PUSH_SERVICE_TOKEN='test-runtime-key'):
            sealed=c.cipher().encrypt(json.dumps(self.state).encode())
            self.assertNotIn(b'test-secret',sealed)
            self.assertEqual(json.loads(c.cipher().decrypt(sealed)),self.state)
        with patch.dict('os.environ',PUSH_SERVICE_TOKEN=''):
            with self.assertRaises(ValueError):c.cipher()
    def test_exchange_uses_fixed_endpoint_and_rejects_broad_scope(self):
        class Response(io.BytesIO):
            pass
        reply={'token_type':'Bearer','scope':c.SCOPE,'refresh_token':'r'*30}
        with patch.object(c,'build_opener') as opener:
            opener.return_value.open.return_value=Response(json.dumps(reply).encode())
            result=c.exchange(self.state['client'],{'verifier':'v'*64},'code')
            self.assertEqual(opener.return_value.open.call_args.args[0].full_url,'https://oauth2.googleapis.com/token')
            self.assertEqual(result['scopes'],[c.SCOPE])
            for bad in ({**reply,'scope':'https://www.googleapis.com/auth/drive'},{**reply,'refresh_token':''}):
                opener.return_value.open.return_value=Response(json.dumps(bad).encode())
                with self.assertRaises(ValueError):c.exchange(self.state['client'],{'verifier':'v'*64},'code')

class WebTests(unittest.TestCase):
    def handler(self,path='/archive/connect',method='GET',headers=None,body=b''):
        class Handler:
            def send_response(self,status):self.status=status
            def send_header(self,k,v):self.response_headers[k]=v
            def end_headers(self):pass
        h=Handler();h.path=path;h.command=method;h.headers=headers or {};h.response_headers={};h.wfile=io.BytesIO();h.rfile=io.BytesIO(body)
        return h
    def test_login_before_any_storage(self):
        with patch.object(w.bob_oauth,'configured',return_value=True),patch.object(w.bob_oauth,'browser_ready',return_value=False),patch.object(w,'rpc') as rpc:
            self.assertTrue(w.route(self.handler(),'user','password'));rpc.assert_not_called()
    def test_cross_origin_and_csrf_rejected(self):
        with patch.object(w.bob_oauth,'configured',return_value=True),patch.object(w.bob_oauth,'browser_ready',return_value=True),patch.object(w,'rpc') as rpc,patch.object(w,'csrf',return_value='expected'):
            for origin in ('https://evil.example', 'null', ''):
                h=self.handler('/archive/connect/begin','POST',{'Origin':origin})
                w.route(h,'user','password');self.assertEqual(h.status,403)
            body=b'csrf=wrong'
            h=self.handler('/archive/connect/begin','POST',{'Origin':c.ORIGIN,'Content-Type':'application/x-www-form-urlencoded','Content-Length':str(len(body))},body)
            w.route(h,'user','password');self.assertEqual(h.status,403);rpc.assert_not_called()
    def test_setup_page_no_store_and_fixed_callback(self):
        with patch.object(w.bob_oauth,'configured',return_value=True),patch.object(w.bob_oauth,'browser_ready',return_value=True),patch.object(w,'rpc',return_value={'configured':False}),patch.object(w,'csrf',return_value='csrf'):
            h=self.handler();w.route(h,'user','password')
            self.assertEqual(h.status,200);self.assertEqual(h.response_headers['Cache-Control'],'no-store')
            self.assertEqual(h.response_headers['Referrer-Policy'],'same-origin')
            self.assertIn(c.CALLBACK.encode(),h.wfile.getvalue());self.assertIn(b'type="file"',h.wfile.getvalue())
    def test_strict_cookie_handoff_does_not_exchange_without_login(self):
        with patch.object(w.bob_oauth,'configured',return_value=True),patch.object(w.bob_oauth,'browser_ready') as login,patch.object(w,'rpc') as rpc:
            h=self.handler('/archive/connect/callback?code=test-code&state=nonce');w.route(h,'user','password')
            self.assertEqual(h.status,200);login.assert_not_called();rpc.assert_not_called()
            self.assertIn(b'/archive/connect/finish?',h.wfile.getvalue())
            self.assertEqual(h.response_headers['Referrer-Policy'],'no-referrer')
    def test_callback_failure_is_redacted(self):
        with patch.object(w.bob_oauth,'configured',return_value=True),patch.object(w.bob_oauth,'browser_ready',return_value=True),patch.object(w,'rpc',side_effect=ValueError('secret-response')):
            h=self.handler('/archive/connect/finish?code=private-code&state=x');w.route(h,'user','password')
            self.assertEqual(h.status,400);self.assertNotIn(b'secret',h.wfile.getvalue());self.assertNotIn(b'private-code',h.wfile.getvalue())

if __name__=='__main__':unittest.main()
