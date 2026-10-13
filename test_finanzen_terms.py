import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import finanzen_terms as f
import product_quotes as q

ISIN = 'DE000FG8NHQ3'
PAGE = Path(__file__).with_name('test_fixtures').joinpath('finanzen_fg8nhq_terms.txt').read_text()


class TermsTests(unittest.TestCase):
    def setUp(self):
        f._CACHE.clear()
        self.backup = dict(state='available', **f.parse_page(PAGE, ISIN))
        self.primary = dict(isin=ISIN, productVerified=True, eligible=False,
                            metadata=dict(status=1, underlyingType='SPOT',
                                          issuerExchangeCode='CBSW', direction='SHORT', currency='CHF'),
                            conditions={'ko': {'value': 4401, 'at': 'issuer-time'}})

    def test_exact_identity_and_missing_terms_without_price_or_invented_clock(self):
        got = self.backup
        self.assertEqual(got['conditions']['strike']['value'], 4400)
        self.assertEqual(got['conditions']['currency']['value'], 'CHF')
        self.assertIsNone(got['conditions']['ko']['at'])
        self.assertFalse(got['conditions']['ko']['conditionVerified'])
        for key in ('bid', 'ask', 'leverage', 'ratio', 'quoteAt'):
            self.assertNotIn(key, got)
            self.assertNotIn(key, got['conditions'])

    def test_wrong_identity_factor_and_challenge_rejected(self):
        for bad in (PAGE.replace(ISIN, 'DE000FG34XV8'),
                    PAGE.replace('Warrant with Knock-Out', 'Faktor-Zertifikat'),
                    PAGE.replace('XD0002747026', 'OTHER'), 'Challenge Validation'):
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                f.parse_page(bad, ISIN)

    def test_merge_only_missing_preserves_primary_and_clearance(self):
        original = copy.deepcopy(self.primary)
        with patch.object(f, 'fetch', return_value=self.backup):
            out = f.apply(self.primary, ISIN)
        self.assertEqual(self.primary, original)
        self.assertEqual(out['conditions']['ko'], original['conditions']['ko'])
        self.assertEqual(out['conditions']['strike']['value'], 4400)
        self.assertFalse(out['eligible'])
        self.assertEqual(out['termsBackup']['state'], 'active')

    def test_wrong_currency_rejected(self):
        self.primary['metadata']['currency'] = 'EUR'
        with patch.object(f, 'fetch', return_value=self.backup):
            out = f.apply(self.primary, ISIN)
        self.assertEqual(out['conditions'], self.primary['conditions'])
        self.assertEqual(out['termsBackup']['state'], 'rejected')

    def test_complete_inactive_unknown_and_future_skip_network(self):
        for change in ({'conditions': self.backup['conditions']},
                       {'productVerified': False}, {'sourceDisabled': True},
                       {'metadata': dict(self.primary['metadata'], status=2)},
                       {'metadata': dict(self.primary['metadata'], underlyingType='FUTURE')}):
            with self.subTest(change=change), patch.object(f, 'fetch') as network:
                f.apply(dict(self.primary, **change), ISIN)
                network.assert_not_called()

    def test_network_failure_cached_and_retains_existing(self):
        with patch.object(f, 'urlopen', side_effect=OSError('offline')) as network:
            one = f.apply(self.primary, ISIN)
            two = f.apply(self.primary, ISIN)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(one['conditions'], self.primary['conditions'])
        self.assertEqual(two['termsBackup']['state'], 'unavailable')

    def test_adapter_is_in_product_pipeline(self):
        with patch.object(q, '_get_quote_primary', return_value=self.primary), \
                patch.object(f, 'fetch', return_value=self.backup), \
                patch('sg_chf.convert_analysis', side_effect=lambda x: x), \
                patch('leverage_backup.apply', side_effect=lambda x: x), \
                patch('secondary_validity.apply', side_effect=lambda x, isin: x):
            out = q._get_quote_bounded(ISIN)
        self.assertEqual(out['conditions']['strike']['value'], 4400)
        self.assertFalse(out['eligible'])


if __name__ == '__main__':
    unittest.main()
