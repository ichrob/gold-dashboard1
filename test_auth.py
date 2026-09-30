import base64
import http.client
import re
import threading
import time
import unittest
from urllib.parse import urlencode
import server
import bob_auth


class AuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.USER, server.PASSWORD = 'test-user', 'test-only-password'
        cls.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join()

    def setUp(self):
        bob_auth.SESSIONS.clear()
        bob_auth.PENDING.clear()
        bob_auth.FAILURES.clear()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        base = {'Host': 'bob.example'}
        base.update(headers or {})
        conn.request(method, path, body=body, headers=base)
        r = conn.getresponse()
        result = r.status, dict(r.getheaders()), r.read(), r.getheaders()
        conn.close()
        return result

    def form(self):
        status, headers, body, _ = self.request('GET', '/login')
        self.assertEqual(status, 200)
        self.assertIn(b'autocomplete="current-password"', body)
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertEqual(headers['Referrer-Policy'], 'same-origin')
        token = re.search(b'name="csrf" value="([^"]+)"', body)[1].decode()
        return token

    def sign_in(self, password='test-only-password', origin='https://bob.example'):
        token = self.form()
        return self.request('POST', '/login', urlencode({'username':'test-user','password':password,'csrf':token}), {'Origin':origin,'Content-Type':'application/x-www-form-urlencoded','Cookie':f'{bob_auth.CSRF_COOKIE}={token}'})

    def test_anonymous_access(self):
        for method in ['GET','HEAD']:
            status, h, _, _ = self.request(method, '/')
            self.assertEqual(status, 303)
            self.assertEqual(h['Location'], '/login')
            self.assertNotIn('WWW-Authenticate', h)
        for path in ['/api/live','/api/mtf','/api/degiro/enrich']:
            status, h, _, _ = self.request('GET', path)
            self.assertEqual(status, 401)
            self.assertNotIn('WWW-Authenticate', h)
        self.assertEqual(self.request('GET','/health')[0],200)

    def test_login_session_logout_expiry(self):
        status, h, _, all_headers = self.sign_in()
        self.assertEqual(status,303)
        session = next(v.split(';')[0] for k,v in all_headers if k=='Set-Cookie' and v.startswith(bob_auth.COOKIE+'='))
        for attribute in ['Secure','HttpOnly','SameSite=Strict']:
            self.assertTrue(any(attribute in v for k,v in all_headers if k=='Set-Cookie'))
        self.assertNotIn('test-only-password', session)
        self.assertEqual(self.request('GET','/',headers={'Cookie':session})[0],200)
        token = session.split('=',1)[1]
        bob_auth.SESSIONS[token] = time.time()-1
        self.assertEqual(self.request('GET','/',headers={'Cookie':session})[0],303)
        bob_auth.SESSIONS[token] = time.time()+10
        self.assertEqual(self.request('POST','/logout',headers={'Cookie':session,'Origin':'https://bob.example'})[0],303)
        self.assertEqual(self.request('GET','/',headers={'Cookie':session})[0],303)

    def test_bad_password_and_csrf(self):
        self.assertEqual(self.sign_in(password='wrong')[0],200)
        self.assertFalse(bob_auth.SESSIONS)
        self.assertEqual(self.sign_in(origin='https://other.example')[0],403)
        self.assertFalse(bob_auth.SESSIONS)
        self.assertEqual(self.sign_in(origin='null')[0],403)
        self.assertEqual(self.sign_in(origin='')[0],403)
        token = self.form()
        body = urlencode({'username':'test-user','password':'test-only-password','csrf':token})
        self.assertEqual(self.request('POST','/login',body,{'Origin':'https://bob.example','Content-Type':'application/x-www-form-urlencoded'})[0],403)

    def test_forged_session_and_cookie_csrf(self):
        self.assertEqual(self.request('GET','/',headers={'Cookie':bob_auth.COOKIE+'=forged'})[0],303)
        self.assertEqual(self.request('POST','/api/push/send','{}',{'Cookie':bob_auth.COOKIE+'=forged','Origin':'https://other.example'})[0],403)

    def test_basic_auth_compatibility_and_worker(self):
        basic = 'Basic '+base64.b64encode(b'test-user:test-only-password').decode()
        self.assertEqual(self.request('GET','/',headers={'Authorization':basic})[0],200)
        self.assertEqual(self.request('GET','/',headers={'Authorization':'Basic broken'})[0],303)

    def test_rate_limit(self):
        bob_auth.FAILURES.extend([time.time()]*30)
        self.assertEqual(self.sign_in()[0],429)
        self.assertFalse(bob_auth.SESSIONS)


if __name__ == '__main__':
    unittest.main()
