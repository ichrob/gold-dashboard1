import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import public_product_terms as p
import product_quotes as q

ISIN='DE000FG5GUT0'
NOW=datetime(2026,10,3,18,tzinfo=timezone.utc)
PAGE='''<h2>WKN: FG5GUT ISIN: DE000FG5GUT0</h2>
Stammdaten Typ Hebel-Bull-Zertifi.. Knock Out 4.069,2502 USD Basispreis 4.069,2502 USD
Laufzeitende endlos Letzter Handelstag -- Bewert.-Tag -- Bez.-Verh. 10 : 1 Emittent Société Générale
Währung EUR Währungs­gesichert Nein Symbol -- ISIN DE000FG5GUT0 WKN FG5GUT Zielmarktkriterien Anzeigen
Kennzahlen Hebel -- Knock Out erreicht Nein
<table><tr><th>Basiswert</th><td><a href="/inf/rohstoffe/goldpreis-XC0009655157">Gold</a></td></tr></table>'''

class PublicTermsTests(unittest.TestCase):
    def test_exact_terms_without_invented_quote_clocks(self):
        r=p.parse_page(PAGE,ISIN,NOW)
        self.assertEqual(r['metadata']['ratio'],.1)
        self.assertEqual(r['metadata']['underlying'],'XAU/USD')
        self.assertEqual(r['metadata']['ko'],4069.2502)
        self.assertIsNone(r['observedTerms']['effectiveAt'])
        self.assertFalse(r['eligible']);self.assertNotIn('bidAt',r)
    def test_identity_and_navigation_link_do_not_prove_underlying(self):
        for html in [PAGE.replace('WKN: FG5GUT','WKN: FG309G'),PAGE.replace('<th>Basiswert</th>','<th>Navigation</th>'),PAGE.replace('10 : 1','-- : 1'),PAGE.replace('Gold</a>','Silver</a>')]:
            with self.assertRaises(ValueError):p.parse_page(html,ISIN,NOW)
    def test_contract_month_and_exchange_required(self):
        html=PAGE.replace('<th>Basiswert</th>','<th>Navigation</th>')+' Strategie / Bemerkung Basiswert Gold Future 12/2026 (COMEX) USD Handelsplätze'
        r=p.parse_page(html,ISIN,NOW)
        self.assertEqual(r['metadata']['contract'],'GCZ26')
        self.assertNotIn('contract',r['conditions'])
        with self.assertRaises(ValueError):p.parse_page(html.replace('(COMEX)',''),ISIN,NOW)
    def test_terminal_evidence_survives_missing_page_and_never_calls_sources(self):
        with patch.object(p,'open_public_page') as network,patch.object(q,'get_issuer_quote') as issuer:
            r=q.get_quote('DE000FG7MTA6')
            network.assert_not_called();issuer.assert_not_called()
        self.assertEqual(r['metadata']['status'],2);self.assertFalse(r['eligible'])
    def test_no_more_stuttgart_requests(self):
        terms=p.parse_page(PAGE,ISIN,NOW)
        with patch.object(p,'get_product',return_value=terms),patch.object(q,'get_issuer_quote',return_value={'found':False}),patch('stuttgart_products.urlopen') as old:
            r=q.get_quote(ISIN)
            self.assertEqual(r['source'],terms['source']);old.assert_not_called()
    def test_dated_issuer_does_not_wait_for_secondary_or_accept_older_terms(self):
        primary = dict(isin=ISIN, productVerified=True, found=False, eligible=False,
                       metadata=dict(status=1, termsDated=True),
                       conditions={'ko': {'value':4074.353817, 'dateText':'07.10.2026'}})
        with patch.object(q,'get_issuer_quote',return_value=primary), patch.object(p,'get_product') as secondary:
            result=q.get_quote(ISIN)
        secondary.assert_not_called()
        self.assertEqual(result['conditions'],primary['conditions'])
        self.assertFalse(result['eligible'])

    def test_secondary_remains_available_when_primary_unavailable(self):
        fallback=p.parse_page(PAGE,ISIN,NOW)
        calls=[]
        def primary(_):
            calls.append('issuer'); return dict(found=False, productVerified=False)
        def secondary(_):
            calls.append('secondary'); return fallback
        with patch.object(q,'get_issuer_quote',side_effect=primary), patch.object(p,'get_product',side_effect=secondary):
            result=q.get_quote(ISIN)
        self.assertEqual(calls,['issuer','secondary'])
        self.assertEqual(result['conditions'],fallback['conditions'])
        self.assertFalse(result['eligible'])

    def test_403_cached_as_failure_and_not_retried_in_a_loop(self):
        from urllib.error import HTTPError
        with patch.dict(p._CACHE,{},clear=True),patch.object(p,'open_public_page',side_effect=HTTPError('public',403,'Denied',{},None)) as net:
            a=p.get_product(ISIN);b=p.get_product(ISIN)
            self.assertEqual(a['sourceFailureCode'],'HTTP_403');self.assertEqual(net.call_count,1)

if __name__=='__main__':unittest.main()
