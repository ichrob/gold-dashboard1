import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import stuttgart_products as s
import product_quotes as q

ISIN='DE000FG309G0'
NOW=datetime(2026,10,3,18,tzinfo=timezone.utc)
PAGE='''Stammdaten WKN FG309G ISIN DE000FG309G0 Symbol - Optionsart put
Basiswert Gold Future 12/2026 (COMEX) USD Basispreis in [Währung] 4.635,8091 [USD]
Knockout-Barriere 4.635,8091 [USD] Cap in [Währung] - Bezugsverhältnis 0,10 Ausübungsart Bermuda
Nominalwährung EUR Abwicklungswährung Euro Letzter Bewertungstag Endlos Zahltag -
Letzter Börsenhandelstag Endlos Handelszeit 08:00:00 - 22:00:00 Produktbeschreibung'''

class StuttgartTests(unittest.TestCase):
    def test_identity_contract_and_no_invented_times(self):
        r=s.parse_page(PAGE,ISIN,NOW)
        self.assertEqual(r['metadata']['contract'],'GCZ26')
        self.assertEqual(r['metadata']['ratio'],.1)
        self.assertEqual(r['metadata']['strike'],4635.8091)
        self.assertFalse(r['found']);self.assertFalse(r['eligible'])
        self.assertIsNone(r['observedTerms']['effectiveAt'])
        self.assertNotIn('strike',r['conditions'])
        self.assertNotIn('contract',r['conditions'])
        self.assertNotIn('quoteAt',r)
    def test_wrong_identity_currency_and_unknown_underlying_rejected(self):
        for bad in [PAGE.replace(ISIN,'DE000FG7MTA6'),PAGE.replace('[USD]','[EUR]'),PAGE.replace('Gold Future 12/2026 (COMEX) USD','Silver Spot')]:
            with self.assertRaises(ValueError):s.parse_page(bad,ISIN,NOW)
    def test_knockout_and_expiry(self):
        for page in ['Das Wertpapier wurde ausgeknockt. '+PAGE,PAGE.replace('Letzter Börsenhandelstag Endlos','Letzter Börsenhandelstag 01.10.2026')]:
            self.assertEqual(s.parse_page(page,ISIN,NOW)['metadata']['status'],2)
    def test_terms_reach_existing_api(self):
        terms=s.parse_page(PAGE,ISIN,NOW)
        with patch.object(s,'get_product',return_value=terms),patch.object(q,'get_issuer_quote',return_value={'found':False}):
            self.assertEqual(q.get_quote(ISIN),terms)
    def test_knockout_overrides_issuer_eligibility(self):
        terms=s.parse_page('Das Wertpapier wurde ausgeknockt. '+PAGE,ISIN,NOW)
        with patch.object(s,'get_product',return_value=terms),patch.object(q,'get_issuer_quote',return_value={'found':True,'eligible':True}):
            self.assertFalse(q.get_quote(ISIN)['eligible'])
    def test_failed_exchange_keeps_issuer_quote(self):
        with patch.object(s,'get_product',return_value={'productVerified':False}),patch.object(q,'get_issuer_quote',return_value={'found':True,'bid':12}):
            self.assertEqual(q.get_quote(ISIN)['bid'],12)
    def test_invalid_isin_never_requests(self):
        with patch.object(s,'urlopen') as fetch:
            self.assertFalse(s.get_product('bad')['productVerified']);fetch.assert_not_called()

if __name__=='__main__':unittest.main()
