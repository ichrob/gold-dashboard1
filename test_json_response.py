import io
import json
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import MagicMock, patch

from json_response import encoded_response, BUFFER_BYTES


class JsonResponseTests(unittest.TestCase):
    def test_wire_format_and_cleanup(self):
        for payload in ({'text': 'Gold € ä 😀', 'values': [None, True, 1.5]},
                        {'image': 'x' * 900000}, {'rows': [{'n': n} for n in range(40000)]}):
            with encoded_response(payload) as (stream, length):
                expected = json.dumps(payload, separators=(',', ':')).encode()
                self.assertEqual(stream.read(), expected)
                self.assertEqual(length, len(expected))
            self.assertTrue(stream.closed)

    def test_large_history_uses_bounded_serialization_memory(self):
        # tracemalloc is process-wide: background workers started by other
        # integration tests must not be charged to this serializer.
        result = subprocess.run([sys.executable, '-c', textwrap.dedent('''
            import json, tracemalloc
            from json_response import encoded_response, BUFFER_BYTES
            payload = {'rows': [{'id': n, 'source': 'x' * 200} for n in range(40000)]}
            tracemalloc.start()
            with encoded_response(payload) as (stream, length):
                peak = tracemalloc.get_traced_memory()[1]
                while stream.read(BUFFER_BYTES):
                    pass
            print(json.dumps({'length': length, 'peak': peak}))
        ''')], check=True, capture_output=True, text=True, timeout=60)
        measurement = json.loads(result.stdout)
        self.assertGreater(measurement['length'], 8_000_000)
        self.assertLess(measurement['peak'], 2_000_000)

    def test_serialization_failure_precedes_headers(self):
        import push_server
        handler = MagicMock()
        with self.assertRaises(TypeError):
            push_server.send_json(handler, 200, {'invalid': object()})
        handler.send_response.assert_not_called()

    def test_http_length_and_disconnect(self):
        import push_server
        handler = MagicMock()
        handler.wfile = io.BytesIO()
        payload = {'rows': ['abcd' * 100 for _ in range(3000)]}
        with patch.object(push_server, 'cors'):
            push_server.send_json(handler, 200, payload)
        body = handler.wfile.getvalue()
        self.assertEqual(json.loads(body), payload)
        handler.send_header.assert_any_call('Content-Length', str(len(body)))
        handler.wfile = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError()
        handler.reset_mock()
        with patch.object(push_server, 'cors'):
            push_server.send_json(handler, 200, payload)
        self.assertTrue(handler.close_connection)
        handler.send_response.assert_called_once_with(200)


if __name__ == '__main__':
    unittest.main()

