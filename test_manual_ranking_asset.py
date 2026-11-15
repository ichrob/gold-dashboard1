"""Route-level regression: manual ranking bundle must be served by Bob's real HTTP handler."""
import unittest
from unittest.mock import Mock
import server


class ManualRankingStaticAssetTests(unittest.TestCase):
    def test_manual_ranking_asset_exact_public_path_and_safe_headers(self):
        handler = object.__new__(server.Handler)
        handler.path = '/manual_ranking_order.js?v=20261112-screen-reconcile-v4'
        handler.headers = {}
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = Mock()
        handler.authenticated = Mock(return_value=False)
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        headers = [call.args for call in handler.send_header.call_args_list]
        self.assertIn(('Content-Type', 'application/javascript; charset=utf-8'), headers)
        self.assertIn(('Cache-Control', 'no-store'), headers)
        self.assertIn(('X-Content-Type-Options', 'nosniff'), headers)
        data = handler.wfile.write.call_args.args[0]
        self.assertIn(b'BobManualTop3', data)
        self.assertIn(b'reconcileBrokerDisplay', data)
        self.assertIn(b'orderSubmitted:false', data)
        self.assertNotIn(b'/api/degiro/order', data)


if __name__ == '__main__':
    unittest.main()
