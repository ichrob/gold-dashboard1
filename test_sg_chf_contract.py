"""Synthetic contract fixtures; no product quotes or broker permissions."""
import copy
import io
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from datetime import datetime, timezone
import sg_chf_contract as c
import handset_contract_model as h
from test_handset_contract_model import record, ISIN, NOW

URL=c.API+'Downloads/document/'+ISIN+'_KID/Zml4dHVyZQ=='
TEXT='''Basisinformationsblatt
PRODUKT Classic TURBO-Optionsscheine (Put) bezogen auf Gold (Non-Quanto)
ISIN: DE000FG8NHQ3 / HERSTELLER: Société Générale
ERSTELLUNGSDATUM DES BASISINFORMATIONSBLATTS: 6. November 2026
Die Umrechnung in die Währung des Produkts erfolgt auf Basis des maßgeblichen Wechselkurses am Bewertungstag.
Basiswert: Gold (unallocated gold) gemäß den Regeln der LBMA (Gold)
Währung des Basiswerts: US-Dollar (USD)
Währung des Produkts (Emissionswährung): Schweizer Franken (CHF)
Typ: Put Bezugsverhältnis: 0,10 Basispreis: USD 4.400,00 Knock-out Barriere: USD 4.400,00
Ausübungstag: 19. März 2027 Fälligkeitstag: 30. März 2027
'''

def proof(text=TEXT):return c.parse_text(text,ISIN,URL,'a'*64,NOW)

class IssuerContractTests(unittest.TestCase):
    def setUp(self):c._CACHE.clear()
    def test_explicit_non_quanto_and_exercise_date(self):
        p=proof()
        self.assertIs(p['quanto'],False)
        self.assertEqual((p['ratio'],p['ko'],p['strike']),(.1,4400,4400))
        self.assertEqual(p['maturity'],'19.03.2027')
        self.assertEqual(p['settlementDate'],'2027-03-30')
        self.assertEqual(proof(TEXT.replace('Put','Call'))['direction'],'LONG')

    def test_missing_wrong_ambiguous_and_future_contract_rejected(self):
        changes=[('Non-Quanto','Quanto'),('Gold (unallocated gold)','Silver'),
            ('Schweizer Franken (CHF)','Euro (EUR)'),('ISIN: '+ISIN,'ISIN: DE000FG0SGZ2'),
            ('HERSTELLER: Société Générale','HERSTELLER: Other'),
            ('Typ: Put','Typ: Call'),('6. November 2026','14. November 2026'),
            ('19. März 2027','12. November 2026'),('30. März 2027','18. März 2027'),
            ('maßgeblichen Wechselkurses','festen Kurses'),
            ('Bezugsverhältnis: 0,10','Bezugsverhältnis: 0,10 Bezugsverhältnis: 0,20')]
        for a,b in changes:
            with self.subTest(a=a),self.assertRaises((ValueError,KeyError)):proof(TEXT.replace(a,b))
        for url in [URL.replace('.ch/','.ch.evil/'),URL+'?url=evil',URL.replace(ISIN,'DE000FG0SGZ2')]:
            with self.assertRaises(ValueError):c.parse_text(TEXT,ISIN,url,'a'*64,NOW)

    def test_403_backup_recovered_without_mutating_clocks_or_permissions(self):
        q=record();q['termsBackup']={'state':'unavailable','code':'HTTP_403'}
        q['bidAt']='original';before=copy.deepcopy(q)
        with patch.object(c,'fetch',return_value=dict(state='active',currencyTreatment=proof())):
            out=c.apply(q,ISIN)
        self.assertEqual(q,before)
        model=h.prepare(out,NOW)
        self.assertTrue(model['handsetModelCheck']['modelAttached'])
        self.assertEqual(model['handsetModelCheck']['evidenceKind'],'sg-kid')
        self.assertEqual(model['bidAt'],'original');self.assertFalse(model['eligible'])
        self.assertEqual(model['conditions'],q['conditions'])
        self.assertTrue(model['productModel']['researchOnly'])

    def test_conflicting_issuer_evidence_blocks_secondary_model(self):
        q=record();p=proof();p['ratio']=.2
        with patch.object(c,'fetch',return_value=dict(state='active',currencyTreatment=p)):
            out=c.apply(q,ISIN)
        self.assertEqual(out['issuerContractCheck']['code'],'KID_TERMS_MISMATCH')
        self.assertNotIn('productModel',h.attach(out,NOW))

    def test_inactive_or_other_product_never_fetches(self):
        for field,value in [('status',2),('currency','EUR'),('classificationId',45)]:
            q=record();q['metadata'][field]=value
            with patch.object(c,'fetch',side_effect=AssertionError('network')):self.assertIs(c.apply(q,ISIN),q)

    def test_failure_cached_and_no_html_or_redirect_accepted(self):
        with patch('product_quotes.issuer_json',side_effect=HTTPError('url',403,'Denied',{},None)) as fetch:
            self.assertEqual(c.fetch(ISIN)['code'],'HTTP_403')
            self.assertEqual(c.fetch(ISIN)['code'],'HTTP_403');self.assertEqual(fetch.call_count,1)
        product=dict(Isin=ISIN,Id=123,ProductClassificationId=43,Currency='CHF',
                     ExchangeCode='CBSW',AssetCurrency='USD',AssetNMP='XAUUSD')
        docs=[dict(Name='Basisinformationsblatt',LinkType=0,FileType=0,Href=URL[len(c.ORIGIN):])]
        for body,url,expected in [(b'<html>login</html>',URL,'KID_INVALID_PDF'),
                                  (b'%PDF-1.5',URL+'?wrong','KID_UNEXPECTED_REDIRECT'),
                                  (b'%PDF-'+b'a'*500000,URL,'KID_INVALID_PDF')]:
            c._CACHE.clear();response=MagicMock();response.__enter__.return_value=response
            response.url=url;response.read.return_value=body
            with patch('product_quotes.issuer_json',side_effect=[product,docs]),patch.object(c,'urlopen',return_value=response):
                self.assertEqual(c.fetch(ISIN)['code'],expected)

    def test_pdf_download_parsing_and_success_cache(self):
        from pypdf import PdfReader
        product=dict(Isin=ISIN,Id=123,ProductClassificationId=43,Currency='CHF',
                     ExchangeCode='CBSW',AssetCurrency='USD',AssetNMP='XAUUSD')
        docs=[dict(Name='Basisinformationsblatt',LinkType=0,FileType=0,Href=URL[len(c.ORIGIN):])]
        response=MagicMock();response.__enter__.return_value=response;response.url=URL;response.read.return_value=b'%PDF-fixture'
        reader=MagicMock();reader.is_encrypted=False;reader.pages=[MagicMock()];reader.pages[0].extract_text.return_value=TEXT
        with patch('product_quotes.issuer_json',side_effect=[product,docs]),patch.object(c,'urlopen',return_value=response),patch('pypdf.PdfReader',return_value=reader) as pdf,patch.object(c,'datetime') as clock:
            clock.now.return_value=NOW;clock.side_effect=datetime
            result=c.fetch(ISIN);self.assertEqual(result['state'],'active')
            self.assertEqual(c.fetch(ISIN),result);self.assertEqual(pdf.call_count,1)
            result['currencyTreatment']['ratio']=99
            self.assertEqual(c.fetch(ISIN)['currencyTreatment']['ratio'],.1)

if __name__=='__main__':unittest.main()
