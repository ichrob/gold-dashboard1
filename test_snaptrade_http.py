import json
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from test_degiro_readonly_http import ReadOnlyHTTPTest
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request


class SnapTradeHTTPTest(ReadOnlyHTTPTest):
    def test_status_is_authenticated_and_never_triggers_provider_requests(self):
        with patch.object(self.server_module.snaptrade_bridge, 'api_get') as get:
            with self.assertRaises(HTTPError) as e:
                urlopen(self.request('/api/snaptrade/status', auth=False), timeout=5)
            self.assertEqual(e.exception.code, 401)
            with urlopen(self.request('/api/snaptrade/status'), timeout=5) as r:
                self.assertEqual(r.headers.get('Cache-Control'), 'no-store')
                data = json.load(r); self.assertFalse(data['realOrders'])
            get.assert_not_called()

    def test_configure_checks_origin_and_does_not_echo_keys(self):
        bridge = self.server_module.snaptrade_bridge
        with patch.object(bridge, 'handle', return_value={'code': 'READY'}) as handle:
            for auth, origin, code in ((False, True, 401), (True, False, 403)):
                with self.assertRaises(HTTPError) as e:
                    urlopen(self.request('/api/snaptrade/configure', auth, origin, b'{}'), timeout=5)
                self.assertEqual(e.exception.code, code)
            handle.assert_not_called()
        with patch.object(bridge, 'handle', side_effect=ValueError('DO_NOT_ECHO')):
            with self.assertRaises(HTTPError) as e:
                urlopen(self.request('/api/snaptrade/configure', body=b'{}'), timeout=5)
            self.assertEqual(e.exception.code, 400)
            self.assertNotIn(b'DO_NOT_ECHO', e.exception.read())

    def test_no_broker_write_route_added(self):
        with patch.object(self.server_module.snaptrade_bridge, 'handle') as handle:
            with self.assertRaises(HTTPError):
                urlopen(self.request('/api/snaptrade/order', body=b'{}'), timeout=5)
            handle.assert_not_called()

    def test_infrastructure_failures_return_json_without_keys(self):
        bridge = self.server_module.snaptrade_bridge
        for failure in (bridge.ReadError('CRYPTO_UNAVAILABLE'), RuntimeError('DO_NOT_ECHO')):
            with self.subTest(failure=type(failure).__name__), patch.object(bridge, 'handle', side_effect=failure):
                with self.assertRaises(HTTPError) as e:
                    urlopen(self.request('/api/snaptrade/configure', body=b'{}'), timeout=5)
                self.assertEqual(e.exception.code, 503)
                body = e.exception.read()
                self.assertNotIn(b'DO_NOT_ECHO', body)
                self.assertIn(json.loads(body)['code'], ('CRYPTO_UNAVAILABLE', 'SETUP_FAILED'))


class SnapTradePrivateStoreHTTPTest(unittest.TestCase):
    def test_service_token_required_before_settings_access(self):
        try:
            import push_server
        except ImportError:
            self.skipTest('Push dependencies installed in full CI')
        with patch.object(push_server, 'PUSH_SERVICE_TOKEN', 'private-store-test-token'), patch.object(push_server, 'db') as db:
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), push_server.Handler)
            worker = threading.Thread(target=httpd.serve_forever, daemon=True); worker.start()
            url = 'http://127.0.0.1:' + str(httpd.server_port) + '/snaptrade-settings/read'
            try:
                with self.assertRaises(HTTPError) as e: urlopen(Request(url, data=b'{}'), timeout=5)
                self.assertEqual(e.exception.code, 401); db.assert_not_called()
                with patch.object(push_server.snaptrade_settings, 'handle', return_value={'sealed': None}) as handle:
                    with urlopen(Request(url, data=b'{}', headers={'X-Bob-Push-Token': 'private-store-test-token'}), timeout=5) as r:
                        self.assertEqual(json.load(r), {'sealed': None})
                        self.assertEqual(r.headers.get('Cache-Control'), 'no-store')
                    handle.assert_called_once()
            finally:
                httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)
