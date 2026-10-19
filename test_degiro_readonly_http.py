import base64
import json
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from test_vollautomatisch_http import PaperHTTPTest


class ReadOnlyHTTPTest(PaperHTTPTest):
    def request(self, path, auth=True, origin=True, body=None):
        base=self.url.split('/api/')[0]
        headers={}
        if auth:
            token=base64.b64encode((self.server_module.USER+':'+self.server_module.PASSWORD).encode()).decode()
            headers['Authorization']='Basic '+token
        if origin:
            headers['Origin']=base.replace('http://','https://')
        return Request(base+path, data=body, headers=headers)

    def test_status_requires_login(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.request('/api/degiro/connection-status',auth=False),timeout=5)
        self.assertEqual(error.exception.code,401)

    def test_probe_requires_login_and_origin(self):
        with patch.object(self.server_module.degiro_readonly,'probe') as probe:
            for auth,origin,expected in ((False,True,401),(True,False,403)):
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.request('/api/degiro/connection-test',auth,origin,b'{}'),timeout=5)
                self.assertEqual(error.exception.code,expected)
            probe.assert_not_called()

    def test_probe_only_accepts_otp(self):
        with patch.object(self.server_module.degiro_readonly,'probe') as probe:
            with self.assertRaises(HTTPError) as error:
                urlopen(self.request('/api/degiro/connection-test',body=b'{"password":"not-accepted"}'),timeout=5)
            self.assertEqual(error.exception.code,400)
            probe.assert_not_called()

    def test_authenticated_probe_response_not_cached(self):
        with patch.object(self.server_module.degiro_readonly,'probe',return_value={'ok':False,'code':'SETUP_REQUIRED'}) as probe:
            with urlopen(self.request('/api/degiro/connection-test',body=b'{"otp":"001234"}'),timeout=5) as response:
                self.assertEqual(response.headers.get('Cache-Control'),'no-store')
                self.assertEqual(json.load(response)['code'],'SETUP_REQUIRED')
            probe.assert_called_once_with('001234', [])
