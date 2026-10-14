"""Safe issuer-ID discovery for two SG products from the current DEGIRO list."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import product_quotes as quotes
import sg_direct


class SGDiscoveryTests(unittest.TestCase):
    def setUp(self):
        sg_direct._CACHE.clear()
        sg_direct._TERMS.clear()
        self.time = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
        self.points = [{'Bid': 8.0, 'Ask': 8.01, 'Date': self.time}]

    def fixture(self, isin, venue, currency, product_id):
        product = dict(
            Id=product_id, Isin=isin, ExchangeCode=venue,
            AssetNMP='XAUUSD', AssetCurrency='USD', Currency=currency,
            Status=65, ProductClassificationId=43,
            MaturityDate='2026-10-16T00:00:00',
        )
        props = [dict(Name=name, Value=value, Suffix=suffix) for name, value, suffix in (
            ('Isin', isin, ''),
            ('PutOrCall', 'Call' if isin == 'DE000FG7N6Z2' else 'Put', ''),
            ('BarrierTurboCertificate', 4105 if currency == 'EUR' else 4400, 'USD'),
            ('Ratio', 10, ':1'),
            ('Strike', 4105 if currency == 'EUR' else 4400, 'USD'),
            ('ClassificationName', 'Classic Turbo-Optionsscheine', ''),
            ('IsQuanto', False, ''),
        )]
        return product, props

    def test_market_channels_are_explicit(self):
        self.assertEqual(quotes.sg_market('DE000FG14AV8')[1:], ('CBSW', 'CHF'))
        self.assertEqual(quotes.sg_market('DE000FG7N6Z2')[1:], ('CBDE', 'EUR'))
        self.assertEqual(quotes.sg_market('DE000FG8NHQ3')[1:], ('CBSW', 'CHF'))
        self.assertEqual(quotes.sg_market('DE000FG7K275')[1:], ('CBDE', 'EUR'))

    def test_october_14_list_routes_to_verified_sg_market(self):
        for isin, venue, currency, product_id in (
            ('DE000FG14AV8', 'CBSW', 'CHF', 6901337),
            ('DE000FD0S0G4', 'CBDE', 'EUR', 5824714),
        ):
            with self.subTest(isin=isin):
                product, props = self.fixture(isin, venue, currency, product_id)
                with patch.object(quotes, 'issuer_json', side_effect=[product, props, self.points]) as fetch, \
                     patch.object(quotes, 'get_bnp_quote') as bnp:
                    got = quotes.get_issuer_quote(isin)
                bnp.assert_not_called()
                self.assertTrue(fetch.call_args_list[0].args[0].startswith(quotes.sg_market(isin)[0]))
                self.assertTrue(got['productVerified'])
                self.assertEqual(got['chartEvidence']['currency'], currency)
                self.assertFalse(got['eligible'])

    def test_new_swiss_identity_cannot_accept_german_market(self):
        isin = 'DE000FG14AV8'
        product, props = self.fixture(isin, 'CBDE', 'EUR', 6901337)
        with patch.object(quotes, 'issuer_json', side_effect=[product, props]):
            got = quotes.get_issuer_quote(isin)
        self.assertFalse(got['productVerified'])
        self.assertFalse(got['eligible'])

    def test_verified_issuer_id_permits_research_chart_only(self):
        for isin, venue, currency, product_id in (
            ('DE000FG7N6Z2', 'CBDE', 'EUR', 8162001),
            ('DE000FG8NHQ3', 'CBSW', 'CHF', 8162002),
        ):
            with self.subTest(isin=isin):
                product, props = self.fixture(isin, venue, currency, product_id)
                with patch.object(quotes, 'issuer_json', side_effect=[product, props, self.points]) as fetch, \
                     patch.object(quotes, 'get_bnp_quote') as bnp:
                    got = quotes.get_issuer_quote(isin)
                bnp.assert_not_called()
                self.assertEqual(fetch.call_count, 3)
                self.assertIn('productId=' + str(product_id), fetch.call_args.args[0])
                self.assertTrue(got['productVerified'])
                self.assertEqual(got['chartEvidence']['currency'], currency)
                self.assertFalse(got['found'])
                self.assertFalse(got['eligible'])
                self.assertFalse(got['fresh'])
                self.assertNotIn('leverageAt', got)
                self.assertIsNone(got['conditions']['ko']['at'])

    def test_new_products_are_checked_at_sg_before_bnp(self):
        # These exact ISINs were present in the user's persisted DEGIRO list,
        # but previously were routed only to BNP because SG had no fixed ID.
        for isin in ('DE000FC0WTL1', 'DE000FG5GUP8'):
            with self.subTest(isin=isin):
                product, props = self.fixture(isin, 'CBDE', 'EUR', 8162101)
                self.assertTrue(quotes.sg_on_demand_candidate(isin))
                with patch.object(quotes, 'issuer_json',
                                  side_effect=[product, props, self.points]) as fetch, \
                     patch.object(quotes, 'get_bnp_quote') as bnp:
                    got = quotes.get_issuer_quote(isin)
                bnp.assert_not_called()
                self.assertEqual(fetch.call_count, 3)
                self.assertIn('productId=8162101', fetch.call_args.args[0])
                self.assertTrue(got['productVerified'])
                self.assertEqual(got['chartEvidence']['currency'], 'EUR')
                self.assertFalse(got['found'])
                self.assertFalse(got['eligible'])
                self.assertNotIn('leverageAt', got)

    def test_wrong_issuer_identity_or_venue_never_approves_product(self):
        isin = 'DE000FC0WTL1'
        for change in ({'Isin': 'DE000FG5GUP8'},
                       {'ExchangeCode': 'CBSW', 'Currency': 'CHF'}):
            with self.subTest(change=change):
                sg_direct._CACHE.clear()
                product, props = self.fixture(isin, 'CBDE', 'EUR', 8162102)
                product.update(change)
                with patch.object(quotes, 'issuer_json', side_effect=[product, props]) as fetch:
                    result = sg_direct.get_quote(isin)
                self.assertFalse(result['productVerified'])
                self.assertFalse(result['eligible'])
                self.assertFalse(result['found'])
                self.assertLessEqual(fetch.call_count, 2)

    def test_on_demand_discovery_rejects_non_matching_or_invalid_prefix(self):
        for isin in ('DE000FG8NHQ0', 'DE000PJ9NCK0', 'US0378331005', ''):
            self.assertFalse(quotes.sg_on_demand_candidate(isin))
        with patch.object(quotes, 'get_sg_quote') as sg, \
             patch.object(quotes, 'get_bnp_quote', return_value={'found': False}) as bnp:
            quotes.get_issuer_quote('DE000PJ9NCK0')
        sg.assert_not_called()
        bnp.assert_called_once()

    def test_failed_sg_discovery_falls_back_without_using_sg_chart(self):
        isin = 'DE000FG5GUP8'
        with patch.object(quotes, 'get_sg_quote', return_value={
            'isin': isin, 'productVerified': False, 'reason': 'SG-Identität offen',
            'chartEvidence': {'bid': 1, 'ask': 2}}), \
             patch.object(quotes, 'get_bnp_quote', return_value={
                 'isin': isin, 'found': False, 'productVerified': False}) as bnp:
            result = quotes.get_issuer_quote(isin)
        bnp.assert_called_once()
        self.assertIn('sgDiscovery', result)
        self.assertNotIn('chartEvidence', result)
        self.assertFalse(result['found'])

    def test_wrong_issuer_market_is_rejected_before_chart(self):
        isin = 'DE000FG8NHQ3'
        product, props = self.fixture(isin, 'CBDE', 'EUR', 8162002)
        with patch.object(quotes, 'issuer_json', side_effect=[product, props]) as fetch:
            got = sg_direct.get_quote(isin)
        self.assertFalse(got['productVerified'])
        self.assertFalse(got['eligible'])
        self.assertEqual(fetch.call_count, 2)

    def test_invalid_issuer_id_is_rejected_before_properties(self):
        isin = 'DE000FG7N6Z2'
        product, _ = self.fixture(isin, 'CBDE', 'EUR', 0)
        with patch.object(quotes, 'issuer_json', return_value=product) as fetch:
            got = sg_direct.get_quote(isin)
        self.assertFalse(got['productVerified'])
        self.assertFalse(got['eligible'])
        fetch.assert_called_once()

    def test_undiscovered_id_cannot_be_used_in_chart_parser(self):
        isin = 'DE000FG7N6Z2'
        product, _ = self.fixture(isin, 'CBDE', 'EUR', 8162001)
        with self.assertRaises(ValueError):
            quotes.parse_sg_chart_research(product, self.points, isin)
        parsed = quotes.parse_sg_chart_research(
            product, self.points, isin, verified_id=8162001)
        self.assertFalse(parsed['eligible'])
        self.assertEqual(parsed['chartEvidence']['currency'], 'EUR')


if __name__ == '__main__':
    unittest.main()
