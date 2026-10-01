import hashlib
import http.client
import json
import os
import secrets
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import bob_auth as auth
import bob_session_store as store
import test_auth as baseline


class PersistentLoginTests(unittest.TestCase):
    request = baseline.AuthenticationTests.request
    form = baseline.AuthenticationTests.form
    setUp = baseline.AuthenticationTests.setUp
    @classmethod
    def setUpClass(cls):
        baseline.AuthenticationTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        baseline.AuthenticationTests.tearDownClass.__func__(cls)
    def sign_remember(self):
        from urllib.parse import urlencode
        token=self.form()
        body=urlencode(dict(username='test-user',password='test-only-password',csrf=token,remember='1'))
        return self.request('POST','/login',body,{'Origin':'https://bob.example','Content-Type':'application/x-www-form-urlencoded','Cookie':auth.CSRF_COOKIE+'='+token})

    def test_remember_survives_process_state_loss_and_logout_revokes(self):
        rows={}
        def backend(action,token,user='',password='',expiry=None):
            if action=='create': rows[token]=(user,password,expiry);return {'ok':True}
            if action=='check':return {'valid':bool(token in rows and rows[token][:2]==(user,password) and rows[token][2]>time.time())}
            if action=='revoke':rows.pop(token,None);return {'ok':True}
        with patch.object(auth,'persistent_configured',return_value=True),patch.object(auth,'session_request',side_effect=backend):
            status,_,_,headers=self.sign_remember();self.assertEqual(status,303)
            sc=next(v for k,v in headers if k=='Set-Cookie' and v.startswith(auth.COOKIE+'='))
            self.assertIn('Max-Age=604800',sc)
            cookie=sc.split(';')[0];token=cookie.split('=',1)[1]
            auth.SESSIONS.clear();auth.PENDING.clear()
            self.assertEqual(self.request('GET','/',headers={'Cookie':cookie})[0],200)
            self.assertFalse(auth.authenticated({'Cookie':cookie},'test-user','changed-password'))
            self.assertEqual(self.request('POST','/logout',headers={'Cookie':cookie,'Origin':'https://bob.example'})[0],303)
            auth.SESSIONS.clear()
            self.assertEqual(self.request('GET','/',headers={'Cookie':cookie})[0],303)
            self.assertNotIn(token,rows)

    def test_store_failure_never_grants_access_or_claims_logout(self):
        token='v1_'+secrets.token_urlsafe(32);cookie=auth.COOKIE+'='+token
        with patch.object(auth,'persistent_configured',return_value=True),patch.object(auth,'session_request',side_effect=OSError('fixture')):
            status,_,body,headers=self.sign_remember()
            self.assertEqual(status,200);self.assertIn('momentan nicht verfügbar'.encode(),body)
            self.assertFalse(any(v.startswith(auth.COOKIE+'=') for k,v in headers if k=='Set-Cookie'))
            self.assertFalse(auth.authenticated({'Cookie':cookie},'test-user','test-only-password'))
            self.assertEqual(self.request('POST','/logout',headers={'Cookie':cookie,'Origin':'https://bob.example'})[0],503)


class SessionStoreTests(unittest.TestCase):
    def test_database_binding_expiry_validation_and_revoke(self):
        conn=MagicMock();payload=dict(tokenHash='a'*64,binding='b'*64,expiresAt=10600)
        self.assertEqual(store.handle(conn,'create',payload,10000),{'ok':True})
        sql,params=conn.execute.call_args.args
        self.assertIn('to_timestamp',sql);self.assertEqual(params,('a'*64,'b'*64,10600))
        self.assertTrue(store.handle(conn,'check',payload)['valid'])
        self.assertIn('expires_at > now()',conn.execute.call_args.args[0])
        conn.execute.return_value.fetchone.return_value=None
        self.assertFalse(store.handle(conn,'check',payload)['valid'])
        self.assertTrue(store.handle(conn,'revoke',payload)['ok'])
        self.assertIn('DELETE',conn.execute.call_args.args[0])
        for expiry in (True,float('nan'),10000,10000+store.MAX_TTL+1):
            with self.assertRaises(ValueError):store.handle(conn,'create',dict(payload,expiresAt=expiry),10000)
        with self.assertRaises(ValueError):store.handle(conn,'check',dict(payload,tokenHash="' OR 1=1 --"))

    def test_transport_never_sends_raw_cookie_or_password(self):
        opener=MagicMock();response=opener.open.return_value.__enter__.return_value
        response.read.return_value=b'{"ok":true}'
        token='v1_'+secrets.token_urlsafe(32)
        with patch.object(auth,'STORE_URL','https://push.example'),patch.object(auth,'STORE_TOKEN','service-fixture'),patch.object(auth,'build_opener',return_value=opener):
            auth.session_request('create',token,'fixture-user','fixture-password',time.time()+600)
            request=opener.open.call_args.args[0]
            payload=json.loads(request.data)
            self.assertEqual(payload['tokenHash'],hashlib.sha256(token.encode()).hexdigest())
            self.assertNotIn(token,request.data.decode());self.assertNotIn('fixture-password',request.data.decode())
            self.assertNotIn('fixture-user',request.data.decode())
            self.assertIsNone(auth.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'), 'CI PostgreSQL integration')
class PostgresSessionTests(unittest.TestCase):
    def test_authenticated_http_store_round_trip(self):
        import psycopg
        import push_server
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn) as conn:store.init(conn)
        backend=push_server.ThreadingHTTPServer(('127.0.0.1',0),push_server.Handler)
        thread=threading.Thread(target=backend.serve_forever,daemon=True);thread.start()
        token='v1_'+secrets.token_urlsafe(32)
        try:
            with patch.object(push_server,'db',side_effect=lambda:psycopg.connect(dsn)),patch.object(push_server,'PUSH_SERVICE_TOKEN','ci-service-fixture'),patch.object(auth,'STORE_URL','http://127.0.0.1:'+str(backend.server_address[1])),patch.object(auth,'STORE_TOKEN','ci-service-fixture'):
                self.assertTrue(auth.session_request('create',token,'ci-user','ci-password',time.time()+600)['ok'])
                auth.SESSIONS.clear()
                self.assertTrue(auth.authenticated({'Cookie':auth.COOKIE+'='+token},'ci-user','ci-password'))
                self.assertFalse(auth.authenticated({'Cookie':auth.COOKIE+'='+token},'ci-user','rotated-password'))
                self.assertTrue(auth.session_request('revoke',token)['ok'])
                self.assertFalse(auth.authenticated({'Cookie':auth.COOKIE+'='+token},'ci-user','ci-password'))
        finally:
            backend.shutdown();backend.server_close();thread.join()
    def test_new_connections_retain_sessions_and_revoke(self):
        import psycopg
        dsn=os.environ['BOB_TEST_DATABASE_URL'];digest=secrets.token_hex(32)
        payload=dict(tokenHash=digest,binding=secrets.token_hex(32),expiresAt=time.time()+600)
        with psycopg.connect(dsn) as conn:
            store.init(conn);store.handle(conn,'create',payload)
        with psycopg.connect(dsn) as conn:
            self.assertTrue(store.handle(conn,'check',payload)['valid'])
            self.assertFalse(store.handle(conn,'check',dict(payload,binding='0'*64))['valid'])
            store.handle(conn,'revoke',payload)
        with psycopg.connect(dsn) as conn:
            self.assertFalse(store.handle(conn,'check',payload)['valid'])
            store.handle(conn,'create',payload)
            conn.execute('UPDATE bob_browser_sessions SET expires_at=now()-interval \'1 second\' WHERE token_hash=%s',(digest,))
        with psycopg.connect(dsn) as conn:
            self.assertFalse(store.handle(conn,'check',payload)['valid'])
            store.handle(conn,'revoke',payload)


if __name__=='__main__':unittest.main()
