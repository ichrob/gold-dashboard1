import os
import unittest
from unittest.mock import patch

import product_quotes
import sg_quotes


class SourcePermissionTests(unittest.TestCase):
    def test_sg_issuer_host_is_blocked_before_network(self):
        with patch.object(product_quotes, 'urlopen') as network:
            with self.assertRaisesRegex(PermissionError, 'SG_LIVE_DISABLED_BY_USER'):
                product_quotes.issuer_json(product_quotes.SG_ORIGIN+'EmcWebApi/api/Products/DE000FG4JXV7', product_quotes.SG_ORIGIN)
            network.assert_not_called()

    def test_onvista_never_requests_without_provider_permission(self):
        for config in ({}, {'BOB_ONVISTA_AUTOMATION_APPROVED': 'true'},
                       {'BOB_ONVISTA_AUTOMATION_APPROVED': 'provider-approved'},
                       {'BOB_ONVISTA_PERMISSION_REFERENCE': 'reference'},
                       {'BOB_ONVISTA_AUTOMATION_APPROVED':'provider-approved','BOB_ONVISTA_PERMISSION_REFERENCE':'reference'}):
            with self.subTest(config=config), patch.dict(os.environ, config, clear=True), \
                    patch.object(sg_quotes, 'urlopen') as network:
                with self.assertRaises(PermissionError) as error:
                    sg_quotes.fetch_snapshot('DE000FG4JXV7')
                network.assert_not_called()
                reason = product_quotes.sg_source_error(error.exception, 'dated-quotes')
                self.assertEqual(str(error.exception),'SG_LIVE_DISABLED_BY_USER')

    def test_future_fallback_obeys_same_permission_gate(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sg_quotes, 'urlopen') as network:
            with self.assertRaises(PermissionError):
                sg_quotes.fetch_future_reference()
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
