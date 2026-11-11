import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from bob_gemini_bridge import Bridge, handler_for, MAX_BODY


class BridgeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge(Path('/tmp'), Path('/not-used'))
        self.sent = []
        self.bridge.send = self.sent.append
        self.bridge.session = 'session-1'
        self.bridge.state = 'running'

    def request(self, options=None, session='session-1', details=None):
        self.bridge.receive({'jsonrpc': '2.0', 'id': 'rpc-9', 'method': 'session/request_permission',
                             'params': {'sessionId': session,
                             'toolCall': details or {'title': 'Run tests', 'rawInput': {'command': 'python -m unittest'}},
                             'options': options or [
                                 {'optionId': 'once', 'kind': 'allow_once'},
                                 {'optionId': 'always', 'kind': 'allow_always'},
                                 {'optionId': 'no', 'kind': 'reject_once'}]}})

    def test_permission_requires_explicit_matching_one_shot_decision(self):
        self.request()
        self.assertEqual(self.sent, [])
        snapshot = self.bridge.snapshot()
        entry = snapshot['permissions'][0]
        self.assertEqual([o['id'] for o in entry['options']], ['once', 'no'])
        with self.assertRaises(ValueError):
            self.bridge.permission(entry['id'], 'always')
        self.bridge.permission(entry['id'], 'once')
        self.assertEqual(self.sent[-1]['result']['outcome'], {'outcome': 'selected', 'optionId': 'once'})
        with self.assertRaises(ValueError):
            self.bridge.permission(entry['id'], 'once')

    def test_wrong_session_and_unadvertised_client_tools_fail_closed(self):
        self.request(session='other')
        self.assertEqual(self.sent[-1]['result']['outcome']['outcome'], 'cancelled')
        self.bridge.receive({'id': 22, 'method': 'terminal/create', 'params': {'command': 'echo bad'}})
        self.assertEqual(self.sent[-1]['error']['code'], -32601)
        self.assertFalse(self.bridge.permissions)

    def test_large_command_cannot_be_approved_without_full_display(self):
        self.request(details={'rawInput': {'command': 'x' * 17000}})
        entry = self.bridge.snapshot()['permissions'][0]
        self.assertEqual(entry['options'], [{'id': 'no', 'kind': 'reject_once'}])

    def test_stop_rejects_pending_and_prevents_more_work(self):
        self.request()
        self.bridge.stop()
        self.assertEqual(self.sent[-1]['result']['outcome']['outcome'], 'cancelled')
        self.assertEqual(self.bridge.state, 'stopped')
        with self.assertRaises(ValueError):
            self.bridge.prompt('continue', 'f' * 32)

    def test_expired_and_idle_permissions_cannot_execute(self):
        self.request()
        key = next(iter(self.bridge.permissions))
        self.bridge.permissions[key]['at'] = time.monotonic() - 301
        with self.assertRaises(ValueError):
            self.bridge.permission(key, 'once')
        self.bridge.state = 'ready'
        self.request()
        self.assertEqual(self.sent[-1]['result']['outcome']['outcome'], 'cancelled')

    def test_untrusted_text_is_display_data_not_html_or_execution(self):
        self.bridge.receive({'method': 'session/update', 'params': {'sessionId': 'session-1',
            'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': '<script>bad()</script>'}}}})
        self.assertEqual(self.bridge.snapshot()['events'][-1]['text'], '<script>bad()</script>')
        self.assertEqual(self.sent, [])
        for _ in range(100):
            self.bridge.event('answer', 'x' * 12000)
        self.assertLessEqual(sum(len(e['text']) for e in self.bridge.events), 120000)

    def test_prompt_is_serial_and_not_shell_interpolated(self):
        self.bridge.state = 'ready'
        with patch('bob_gemini_bridge.threading.Thread') as thread:
            self.bridge.prompt('$(touch /tmp/unsafe); "quote"', 'a' * 32)
            self.assertIn('$(touch /tmp/unsafe)', thread.call_args.kwargs['args'][0])
            with self.assertRaises(ValueError):
                self.bridge.prompt('second job', 'b' * 32)
        self.assertEqual(self.sent, [])

    def test_lost_ack_retry_does_not_repeat_development_job(self):
        self.bridge.state = 'ready'
        with patch('bob_gemini_bridge.threading.Thread') as thread:
            self.bridge.prompt('fix', 'a' * 32)
            self.bridge.state = 'ready'
            self.bridge.prompt('fix', 'a' * 32)
            self.assertEqual(thread.call_count, 1)
            with self.assertRaises(ValueError):
                self.bridge.prompt('different change', 'a' * 32)


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.bridge = Bridge(Path('/tmp'), Path('/not-used'))
        self.bridge.state = 'ready'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), lambda *args: None)
        self.port = self.server.server_address[1]
        self.server.RequestHandlerClass = handler_for(self.bridge, 'a' * 64, self.port)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join()

    def call(self, path='/status', method='GET', data=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=2)
        h = {'Authorization': 'Bearer ' + 'a' * 64, 'Content-Type': 'application/json'}
        h.update(headers or {})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse(); status = r.status; payload = r.read(); c.close()
        return status, json.loads(payload)

    def test_correct_local_bearer_only(self):
        self.assertEqual(self.call()[0], 200)
        self.assertEqual(self.call(headers={'Authorization': ''})[0], 403)
        self.assertEqual(self.call(headers={'Origin': 'http://malicious.example'})[0], 403)
        self.assertEqual(self.call(headers={'Host': 'attacker.example'})[0], 403)
        self.assertEqual(self.call('/status?token=' + 'a' * 64)[0], 404)

    def test_invalid_oversized_and_arbitrary_shell_requests_rejected(self):
        self.assertEqual(self.call('/prompt', 'POST', '[]')[0], 400)
        self.assertEqual(self.call('/prompt', 'POST', '{')[0], 400)
        self.assertEqual(self.call('/prompt', 'POST', 'x' * (MAX_BODY + 1))[0], 400)
        self.assertEqual(self.call('/execute', 'POST', '{}')[0], 404)
        self.assertEqual(self.call('/permission', 'POST', '{}')[0], 400)

    def test_stop_route_closes_agent(self):
        self.assertEqual(self.call('/stop', 'POST', '{}')[0], 200)
        self.assertTrue(self.bridge.closed)


class AgentTransportTests(unittest.TestCase):
    def test_actual_stdio_handshake_prompt_and_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder)/'fake-agent'
            executable.write_text("""#!/usr/bin/env python3
import json,sys
session='fixture'
for line in sys.stdin:
    m=json.loads(line); method=m.get('method'); rid=m.get('id')
    if method=='initialize':
        result={'protocolVersion':1}
    elif method=='session/new':
        result={'sessionId':session}
    elif method=='session/prompt':
        prompt_id=rid
        print(json.dumps({'jsonrpc':'2.0','id':'permission-1','method':'session/request_permission','params':{'sessionId':session,'toolCall':{'title':'Fixture command'},'options':[{'optionId':'yes','kind':'allow_once'},{'optionId':'no','kind':'reject_once'}]}}),flush=True)
        continue
    elif rid=='permission-1':
        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'sessionId':session,'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'Rejected safely'}}}}),flush=True)
        rid=prompt_id; result={'stopReason':'end_turn'}
    else:
        continue
    print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
""")
            executable.chmod(0o700)
            bridge = Bridge(Path(folder), executable)
            try:
                bridge.start()
                self.assertEqual(bridge.state, 'ready')
                bridge.prompt('fixture request', '1' * 32)
                end = time.monotonic() + 5
                while not bridge.permissions and time.monotonic() < end:
                    time.sleep(.02)
                key = next(iter(bridge.permissions))
                bridge.permission(key, 'no')
                while bridge.state == 'running' and time.monotonic() < end:
                    time.sleep(.02)
                self.assertEqual(bridge.state, 'ready')
                self.assertTrue(any(e['text']=='Rejected safely' for e in bridge.events))
            finally:
                bridge.stop()
            self.assertIsNotNone(bridge.proc.poll())


class PackageTests(unittest.TestCase):
    def test_signed_asset_and_no_external_entrypoint(self):
        root = Path(__file__).parent
        self.assertEqual((root/'bob_gemini_bridge.py').read_bytes(),
                         (root/'android_companion/app/src/main/assets/bob_gemini_bridge.py').read_bytes())
        manifest = (root/'android_companion/app/src/main/AndroidManifest.xml').read_text()
        self.assertIn('android:name=".GeminiChatActivity" android:exported="false"', manifest)
        source = (root/'bob_gemini_bridge.py').read_text()
        self.assertNotIn('dangerously-skip-permissions', source)
        self.assertNotIn('shell=True', source)


if __name__ == '__main__':
    unittest.main()
