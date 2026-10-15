"""Regression: new stop assistant script served with correct no-store JS headers."""
import unittest
from unittest.mock import Mock
import server

class StopAssistantStaticAssetTests(unittest.TestCase):
    def test_read_only_stop_asset_served_over_exact_public_route(self):
        handler=object.__new__(server.Handler)
        handler.path='/bob_stop_assistant.js?v=20261015-two-stage-v1'
        handler.headers={}
        handler.send_response=Mock()
        handler.send_header=Mock()
        handler.end_headers=Mock()
        handler.wfile=Mock()
        handler.authenticated=Mock(return_value=False)
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        headers=[c.args for c in handler.send_header.call_args_list]
        self.assertIn(('Content-Type','application/javascript; charset=utf-8'),headers)
        self.assertIn(('Cache-Control','no-store'),headers)
        self.assertIn(('X-Content-Type-Options','nosniff'),headers)
        body=handler.wfile.write.call_args.args[0]
        self.assertIn(b'BobStopAssistant',body)
        self.assertIn(b'degiroExecutable:false',body)
        self.assertNotIn(b'/api/degiro/order',body)

if __name__ == '__main__':
    unittest.main()
