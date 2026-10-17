import json
import unittest
from unittest.mock import patch
import degiro_readonly as reader
from degiro_readonly_worker import permitted


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        reader._LAST_ATTEMPT = 0

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
