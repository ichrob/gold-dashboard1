import http.client
import json
import threading
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch
import server


class BackgroundHealthTests(unittest.TestCase):
    def test_health_rejects_stale_failed_and_unconfigured_monitor(self):
        with patch.object(server.time, 'time', return_value=1000), patch.dict(server.FIB_MONITOR_HEALTH, configured=True, status='active', lastSuccessAt=990):
            self.assertEqual(server.background_health()['status'], 'ok')
            with patch.dict(server.FIB_MONITOR_HEALTH, status='checking'):
                self.assertEqual(server.background_health()['status'], 'ok')
            for change in ({'lastSuccessAt': 879}, {'lastSuccessAt': None},
                           {'status': 'unavailable'}, {'configured': False}):
                with patch.dict(server.FIB_MONITOR_HEALTH, change):
                    self.assertEqual(server.background_health()['status'], 'unavailable')

    def cycle(self, background_failure=False, monitor_failure=False, active=1):
        responses = [nullcontext(Mock(read=Mock(return_value=json.dumps({'activeMonitors': active}).encode())))]
        if active:
            responses += [OSError('offline') if background_failure else nullcontext(Mock(read=Mock(return_value=b'{"sent":0}'))),
                          OSError('offline') if monitor_failure else nullcontext(Mock(read=Mock(return_value=b'{"sent":0}')))]
        with patch.object(server, 'PUSH_SERVICE_URL', 'https://push.example'), patch.object(server, 'PUSH_SERVICE_TOKEN', 'test'), patch.object(server, 'urlopen', side_effect=responses), patch.object(server, 'build_live_bundle', return_value={}), patch.object(server.time, 'time', return_value=1000), patch.object(server.time, 'sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                server.fibonacci_monitor_loop()

    def test_only_completed_cycles_advance_success(self):
        for background_failure, monitor_failure in ((True, False), (False, True), (False, False)):
            with self.subTest(background_failure=background_failure, monitor_failure=monitor_failure), patch.dict(server.FIB_MONITOR_HEALTH, configured=True, status='active', lastSuccessAt=900):
                self.cycle(background_failure, monitor_failure)
                failed = background_failure or monitor_failure
                self.assertEqual(server.FIB_MONITOR_HEALTH['lastSuccessAt'], 900 if failed else 1000)
                self.assertEqual(server.FIB_MONITOR_HEALTH['status'], 'unavailable' if failed else 'active')

    def test_idle_cycle_is_healthy(self):
        with patch.dict(server.FIB_MONITOR_HEALTH, configured=True, status='starting', lastSuccessAt=None):
            self.cycle(active=0)
            self.assertEqual(server.FIB_MONITOR_HEALTH['status'], 'idle')
            self.assertEqual(server.FIB_MONITOR_HEALTH['lastSuccessAt'], 1000)

    def test_get_and_head_report_failure_without_exposing_trade_data(self):
        httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            for method in ('GET', 'HEAD'):
                for state, expected in (('active', 200), ('checking', 200), ('unavailable', 503)):
                    with patch.dict(server.FIB_MONITOR_HEALTH, configured=True, status=state, lastSuccessAt=int(server.time.time())):
                        conn = http.client.HTTPConnection(*httpd.server_address)
                        conn.request(method, '/health/background')
                        response = conn.getresponse()
                        self.assertEqual(response.status, expected)
                        body = response.read()
                        if method == 'GET':
                            self.assertNotIn('activeMonitors', json.loads(body))
                        conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join()
