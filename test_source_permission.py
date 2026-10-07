import os
import unittest
from unittest.mock import patch

import product_quotes
import sg_quotes


class SourcePermissionTests(unittest.TestCase):
    def test_sg_authorized_host_can_be_read(self):
        with patch.object(product_quotes, 'urlopen') as network:
            response = network.return_value.__enter__.return_value
            response.url = product_quotes.SG_ORIGIN+'EmcWebApi/api/Products/DE000FG4JXV7'
            response.read.return_value = b'{}'
            self.assertEqual(product_quotes.issuer_json(response.url, product_quotes.SG_ORIGIN), {})
            network.assert_called_once()

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
