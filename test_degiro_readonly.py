import json
import unittest
from unittest.mock import patch
import degiro_readonly as reader
from degiro_readonly_worker import permitted


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        reader._LAST_ATTEMPT = 0
        reader._LAST_RESULT = None

    def test_transport_allowlist_rejects_orders_and_redirect_hosts(self):
        base = 'https://trader.degiro.nl'
        self.assertTrue(permitted('POST', base+'/login/secure/login/totp'))
        self.assertTrue(permitted('GET', base+'/pa/secure/client'))
        self.assertTrue(permitted('GET', base+'/trading/secure/v5/update/123;jsessionid=abc'))
        for method, url in [('POST',base+'/trading/secure/v5/checkOrder'),
                            ('POST',base+'/trading/secure/v5/order'),
                            ('DELETE',base+'/trading/secure/v5/order/1'),
                            ('GET','https://evil.example/pa/secure/client'),
                            ('POST','http://trader.degiro.nl/login/secure/login'),
                            ('GET',base+'/pa/secure/client/extra')]:
            self.assertFalse(permitted(method,url))

    def test_unconfigured_never_launches_sdk(self):
        with patch.object(reader,'status',return_value={'ready':False}), patch.object(reader.subprocess,'run') as launch:
            self.assertEqual(reader.probe()['code'],'SETUP_REQUIRED')
            launch.assert_not_called()

    def test_secret_error_output_is_not_exposed(self):
        with patch.object(reader,'status',return_value={'ready':True}), patch.object(reader.subprocess,'run') as launch:
            launch.return_value.stdout='SECRET session response';launch.return_value.returncode=1
            result=reader.probe('001234')
            self.assertEqual(result['code'],'SDK_ERROR')
            self.assertNotIn('SECRET',json.dumps(result))
            self.assertEqual(json.loads(launch.call_args.kwargs['input'])['otp'],'001234')
            self.assertNotIn('001234',str(launch.call_args.args))
            self.assertEqual(reader.probe()['code'],'COOLDOWN')

    def test_success_only_from_confirmed_read(self):
        with patch.object(reader,'status',return_value={'ready':True}), patch.object(reader.subprocess,'run') as launch:
            launch.return_value.stdout=json.dumps({'code':'READ_OK','logoutConfirmed':True,'sessionId':'SECRET'})
            launch.return_value.returncode=0
            result=reader.probe()
            self.assertTrue(result['portfolioRead']);self.assertFalse(result['liveOrdersEnabled'])
            self.assertNotIn('SECRET',json.dumps(result))

    def test_invalid_otp(self):
        for otp in ('123','12345x',123456):
            with self.assertRaises(ValueError):reader.probe(otp)

    def test_timeout(self):
        with patch.object(reader,'status',return_value={'ready':True}), patch.object(reader.subprocess,'run',side_effect=reader.subprocess.TimeoutExpired('probe',45)):
            self.assertEqual(reader.probe()['code'],'TIMEOUT')


try:
    import degiro_connector
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


@unittest.skipUnless(SDK_AVAILABLE, 'Optional SDK not installed')
class RealSdkContractTests(unittest.TestCase):
    def test_real_sdk_login_read_logout_against_mock_transport(self):
        import requests
        import degiro_readonly_worker
        calls = []
        def send(session, request, **kwargs):
            calls.append(request)
            self.assertEqual(kwargs['timeout'], (5, 8))
            self.assertFalse(kwargs['allow_redirects'])
            if '/login/secure/login' in request.url:
                self.assertEqual(json.loads(request.body)['oneTimePassword'],'001234')
                payload = {'sessionId':'FAKE_SESSION','status':0}
            elif '/pa/secure/client' in request.url:
                payload = {'data':{'intAccount':123}}
            elif '/update/' in request.url:
                payload = {'portfolio':{'value':[]}}
            else:
                payload = {}
            response = requests.Response();response.status_code=200
            response._content=json.dumps(payload).encode();response.request=request
            return response
        with patch.dict(reader.os.environ,{'BOB_DEGIRO_USERNAME':'test','BOB_DEGIRO_PASSWORD':'test'}), patch.object(requests.Session,'send',send):
            result=degiro_readonly_worker.run('001234')
        self.assertEqual(result['code'],'READ_OK')
        self.assertTrue(result['logoutConfirmed'])
        self.assertEqual(len(calls),4)
        self.assertNotIn('FAKE_SESSION',json.dumps(result))

    def test_failed_login_does_not_read_or_hide_auth_error(self):
        import requests
        import degiro_readonly_worker
        def send(session, request, **kwargs):
            response=requests.Response();response.status_code=400
            response._content=b'{"status":6,"statusText":"2fa needed"}'
            return response
        with patch.dict(reader.os.environ,{'BOB_DEGIRO_USERNAME':'test','BOB_DEGIRO_PASSWORD':'test'}), patch.object(requests.Session,'send',send):
            result=degiro_readonly_worker.run('')
        self.assertEqual(result['code'],'AUTH_REQUIRED')
        self.assertFalse(result['logoutConfirmed'])

    def test_broker_login_reasons_are_distinct_and_secret_free(self):
        import requests
        import degiro_readonly_worker as worker
        for status, payload, reason in [
            (400, {'status':6}, 'TOTP_REQUIRED'),
            (400, {'status':12, 'inAppToken':'SECRET'}, 'APP_APPROVAL_REQUIRED'),
            (400, {'status':3, 'captchaRequired':True}, 'CAPTCHA_REQUIRED'),
            (429, {}, 'RATE_LIMITED'), (403, {}, 'ACCESS_DENIED'),
            (503, {}, 'SERVICE_UNAVAILABLE'),
            (400, {'status':3, 'error':'SECRET'}, 'LOGIN_REJECTED'),
            (200, {'status':0}, 'LOGIN_REJECTED'),
        ]:
            calls=[]
            def send(session, request, **kwargs):
                calls.append(request.url)
                response=requests.Response(); response.status_code=status
                response._content=json.dumps(payload).encode(); response.request=request
                return response
            with self.subTest(reason=reason), patch.dict(reader.os.environ,{'BOB_DEGIRO_USERNAME':'fake','BOB_DEGIRO_PASSWORD':'SECRET'}), patch.object(requests.Session,'send',send):
                result=worker.run('')
                self.assertEqual(result['authReason'],reason)
                self.assertNotEqual(result['code'],'READ_OK')
                self.assertEqual(len(calls),1)
                self.assertNotIn('SECRET',json.dumps(result))


class SafeDiagnosticTests(unittest.TestCase):
    def tearDown(self):
        reader._LAST_ATTEMPT=0
        reader._LAST_RESULT=None

    def test_private_diagnostics_keep_probe_reason_without_account_data(self):
        from bob_diagnostics import broker_sync_snapshot
        import degiro_sync
        with patch.object(reader,'_LAST_RESULT',{'code':'AUTH_REQUIRED','authReason':'APP_APPROVAL_REQUIRED','checkedAt':'2026-10-20T07:00:00+00:00'}):
            value=degiro_sync.status()
            value['snapshot']={'observedAt':'2026-10-20T07:00:00+00:00','holdings':['SECRET']}
            report=broker_sync_snapshot(value)
            self.assertEqual(report['lastConnectionTest']['authReason'],'APP_APPROVAL_REQUIRED')
            self.assertNotIn('SECRET',json.dumps(report))

    def test_last_probe_visible_without_secrets_and_cooldown_retains_it(self):
        reader._LAST_ATTEMPT=0; reader._LAST_RESULT=None
        payload={'code':'AUTH_REQUIRED','authReason':'APP_APPROVAL_REQUIRED','inAppToken':'SECRET'}
        with patch.dict(reader.os.environ,{'BOB_DEGIRO_USERNAME':'fake','BOB_DEGIRO_PASSWORD':'SECRET'}), patch.object(reader.subprocess,'run') as launch:
            launch.return_value.stdout=json.dumps(payload); launch.return_value.returncode=0
            result=reader.probe()
            self.assertEqual(result['authReason'],'APP_APPROVAL_REQUIRED')
            self.assertEqual(reader.status()['lastTest']['authReason'],'APP_APPROVAL_REQUIRED')
            self.assertEqual(reader.probe()['code'],'COOLDOWN')
            self.assertEqual(reader.status()['lastTest']['code'],'AUTH_REQUIRED')
            self.assertNotIn('SECRET',json.dumps(reader.status()))

    def test_non_json_login_diagnostic_never_returns_body(self):
        import requests
        from degiro_readonly_worker import login_diagnostic
        response=requests.Response();response.status_code=200;response._content=b'SECRET'
        self.assertEqual(login_diagnostic(response),'INVALID_LOGIN_RESPONSE')

