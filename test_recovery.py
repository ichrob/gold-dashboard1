import base64
import io
import sqlite3
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import bob_recovery as r
import bob_auth as a

class DB:
    def __init__(self):
        self.c = sqlite3.connect(':memory:')
        r.init(self)
        self.execute('CREATE TABLE bob_browser_sessions(token_hash TEXT)')
    def execute(self, sql, args=()):
        return self.c.execute(sql.replace('%s','?').replace(' FOR UPDATE',''), args)

class Handler:
    command = 'POST'
    path = '/forgot-password'
    def __init__(self, fields=None, origin='https://bob.example'):
        fields = dict(fields or {})
        csrf = r.recovery_csrf()
        if fields.get('csrf') == 'test-csrf':fields['csrf'] = csrf
        a.PENDING[csrf] = time.time()+60
        body = urlencode(fields).encode()
        self.headers = {'Host':'bob.example', 'Origin':origin, 'Content-Type':'application/x-www-form-urlencoded','Content-Length':str(len(body)),'Cookie':a.CSRF_COOKIE+'='+csrf+'; '+r.RECOVERY_COOKIE+'='+csrf}
        self.rfile = io.BytesIO(body); self.wfile = io.BytesIO(); self.response_headers = {}
    def send_response(self, status):self.status=status
    def send_header(self,k,v):self.response_headers[k]=v
    def end_headers(self):pass

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.secret_patch=patch.object(a,'STORE_TOKEN','test-only-secret');self.secret_patch.start();self.addCleanup(self.secret_patch.stop)
        self.db=DB(); self.account='a'*64; self.token='b'*64; self.now=10000
        self.data={'account':self.account,'tokenHash':self.token}
        a.SESSIONS.clear();a.PENDING.clear();a.FAILURES.clear()
    def call(self,action,**kw):return r.handle(self.db,action,{**self.data,**kw},self.now)
    def test_initial_and_hash(self):
        state=self.call('state');self.assertTrue(r.matches('original','original',state))
        h=r.hash_password('new-secure-password');self.assertNotIn('new-secure-password',h)
        self.assertTrue(r.matches('new-secure-password','original',{'passwordHash':h}))
        self.assertFalse(r.matches('original','original',{'passwordHash':h}))
    def test_single_use_and_session_revocation(self):
        self.assertTrue(self.call('issue')['issued'])
        self.db.execute("INSERT INTO bob_browser_sessions VALUES('old')")
        h=r.hash_password('new-secure-password')
        self.assertTrue(self.call('reset',passwordHash=h)['ok'])
        self.assertFalse(self.call('reset',passwordHash=h)['ok'])
        self.assertEqual(self.call('state')['version'],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM bob_browser_sessions').fetchone()[0],0)
    def test_expiry_and_wrong_token(self):
        self.call('issue');h=r.hash_password('new-secure-password')
        self.assertFalse(self.call('reset',tokenHash='c'*64,passwordHash=h)['ok'])
        self.now+=901;self.assertFalse(self.call('reset',passwordHash=h)['ok'])
        self.assertIsNone(self.call('state')['passwordHash'])
    def test_rate_limit(self):
        for i in range(5):
            self.assertTrue(self.call('issue')['issued'])
            self.assertFalse(self.call('issue')['issued']);self.now+=61
        self.assertFalse(self.call('issue')['issued']);self.now+=3600
        self.assertTrue(self.call('issue')['issued'])
    def test_cancel(self):
        self.call('issue');self.call('cancel')
        self.assertFalse(self.call('reset',passwordHash=r.hash_password('new-secure-password'))['ok'])
    def test_csrf_and_cross_origin(self):
        a.PENDING['test-csrf']=time.time()+60
        h=Handler({'csrf':'test-csrf'})
        self.assertTrue(r.read_form(h)['csrf'])
        with self.assertRaises(ValueError):r.read_form(Handler({'csrf':'tampered'}))
        with self.assertRaises(ValueError):r.read_form(Handler({'csrf':'test-csrf'},'https://evil.example'))
    def test_csrf_survives_restart_and_login_cookie_change(self):
        h=Handler({'csrf':'test-csrf'})
        a.PENDING.clear()
        h.headers['Cookie']=h.headers['Cookie'].split('; ',1)[1]+'; '+a.CSRF_COOKIE+'=other-login-page'
        self.assertTrue(r.read_form(h)['csrf'])
    def test_csrf_signature_expiry_and_mismatch(self):
        token=r.recovery_csrf()
        self.assertTrue(r.valid_csrf(token,token))
        self.assertFalse(r.valid_csrf(token,token+'x'))
        forged=token[:-1]+('a' if token[-1]!='a' else 'b')
        self.assertFalse(r.valid_csrf(forged,forged))
        with patch.object(r.time,'time',return_value=time.time()+601):
            self.assertFalse(r.valid_csrf(token,token))
    def test_old_sessions_fail_after_reset(self):
        a.SESSIONS['token']=(time.time()+3600,0)
        with patch.object(r,'state',return_value={'passwordHash':None,'version':0}):
            self.assertTrue(a.authenticated({'Cookie':a.COOKIE+'=token'},'user','original'))
        with patch.object(r,'state',return_value={'passwordHash':r.hash_password('new-secure-password'),'version':1}):
            self.assertFalse(a.authenticated({'Cookie':a.COOKIE+'=token'},'user','original'))
            old='Basic '+base64.b64encode(b'user:original').decode()
            new='Basic '+base64.b64encode(b'user:new-secure-password').decode()
            self.assertFalse(a.authenticated({'Authorization':old},'user','original'))
            self.assertTrue(a.authenticated({'Authorization':new},'user','original'))
    def test_store_failure_fails_closed(self):
        with patch.object(r,'state',side_effect=OSError):
            self.assertFalse(a.authenticated({'Authorization':'Basic '+base64.b64encode(b'user:original').decode()},'user','original'))
    def test_unknown_email_never_sends(self):
        a.PENDING['test-csrf']=time.time()+60
        h=Handler({'csrf':'test-csrf','email':'other@example.com'})
        with patch.object(r,'configured',return_value=True),patch.object(r,'email_link') as send,patch.object(r,'rpc') as rpc:
            self.assertTrue(r.route(h,'user'));send.assert_not_called();rpc.assert_not_called();self.assertEqual(h.status,200)
    def test_valid_email_sends_only_fixed_recipient(self):
        a.PENDING['test-csrf']=time.time()+60
        h=Handler({'csrf':'test-csrf','email':r.EMAIL})
        with patch.object(r,'configured',return_value=True),patch.object(r,'email_link') as send,patch.object(r,'rpc',return_value={'issued':True}):
            r.route(h,'user');self.assertEqual(h.status,200);send.assert_called_once()
            self.assertEqual(len(send.call_args.args[0]),43)
    def test_get_does_not_consume(self):
        h=Handler();h.command='GET';h.path='/reset-password?token='+'x'*43
        with patch.object(r,'configured',return_value=True),patch.object(r,'rpc') as rpc:
            r.route(h,'user');rpc.assert_not_called();self.assertEqual(h.status,200)
            self.assertEqual(h.response_headers['Referrer-Policy'],'strict-origin')
    def test_login_new_password_and_session(self):
        a.PENDING['test-csrf']=time.time()+60
        h=Handler({'csrf':'test-csrf','username':'user','password':'new-secure-password'})
        with patch.object(r,'state',return_value={'passwordHash':r.hash_password('new-secure-password'),'version':1}):
            a.login(h,'user','original')
            self.assertEqual(h.status,303);self.assertEqual(len(a.SESSIONS),1)
            self.assertEqual(next(iter(a.SESSIONS.values()))[1],1)

if __name__=='__main__':unittest.main()
