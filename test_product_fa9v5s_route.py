import unittest
from unittest.mock import patch

import product_quotes as q

ISIN = 'DE000FA9V5S0'


class KnownIssuerCandidateTests(unittest.TestCase):
    def test_exact_fa_isin_routes_to_sg_and_preserves_issuer_identity(self):
        self.assertTrue(q.valid_isin(ISIN))
        self.assertTrue(q.sg_on_demand_candidate(ISIN))
        issuer = dict(isin=ISIN, productVerified=True, found=False,
                      source='Société Générale · offizielle Produktdaten')
        with patch.object(q, 'get_sg_quote', return_value=issuer) as sg, \
             patch.object(q, 'get_bnp_quote') as bnp:
            result = q.get_issuer_quote(ISIN)
        self.assertEqual(result, issuer)
        sg.assert_called_once_with(ISIN)
        bnp.assert_not_called()

    def test_no_similar_isin_or_unverified_sg_price_can_be_promoted(self):
        self.assertFalse(q.sg_on_demand_candidate('DE000FA9V5E0'))
        failure = dict(isin=ISIN, productVerified=False, found=False,
                       reason='Emittent bestätigt diesen Abruf nicht')
        fallback = dict(isin=ISIN, productVerified=False, found=False,
                        source='BNP Paribas · öffentliche Produktrecherche')
        with patch.object(q, 'get_sg_quote', return_value=failure), \
             patch.object(q, 'get_bnp_quote', return_value=fallback):
            result = q.get_issuer_quote(ISIN)
        self.assertFalse(result['productVerified'])
        self.assertFalse(result['found'])
        self.assertFalse(result['sgDiscovery']['verified'])


if __name__ == '__main__':
    unittest.main()
