import copy
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
import comdirect_fields as f
import comdirect_quotes as q

ISIN='DE000FG7N6Z2'
HTML=Path(__file__).with_name('test_fixtures').joinpath('comdirect_sg_quote.html').read_text()
NOW=datetime(2026,10,14,tzinfo=timezone.utc)


class ComdirectFieldsTests(unittest.TestCase):
    def parse(self, html=HTML):
        return f.parse_page(html,ISIN,NOW)

    def primary(self):
        return dict(isin=ISIN, productVerified=True, found=False, eligible=False,
                    metadata=dict(status=1, direction='LONG',currency='EUR',underlying='XAU/USD'), conditions={})

    def apply(self, primary=None, fields=None):
        with patch.object(q,'get_observation',return_value=dict(state='observed',fields=fields or self.parse())):
            return f.apply(primary or self.primary(),ISIN)

    def test_partial_page_keeps_other_values(self):
        fields=self.parse(HTML.replace('4.105,0000 USD Basispreis','-- Basispreis'))
        self.assertIn('ko',fields['missing'])
        self.assertEqual(fields['observations']['strike']['value'],4105)
        self.assertEqual(fields['observations']['ratio']['value'],.1)
        self.assertEqual(fields['observations']['direction']['value'],'LONG')
        quote=q.parse_page(HTML.replace('4.105,0000 USD Basispreis','-- Basispreis'),ISIN,NOW)
        self.assertEqual(quote['bid'],5.43)

    def test_missing_values_fill_without_eligibility_or_fake_clock(self):
        out=self.apply()
        self.assertEqual(out['conditions']['ratio']['value'],.1)
        self.assertFalse(out['conditions']['ko']['conditionVerified'])
        self.assertIsNone(out['conditions']['ko']['at'])
        self.assertFalse(out['found']); self.assertFalse(out['eligible'])

    def test_existing_value_and_original_provenance_preserved(self):
        p=self.primary(); p['conditions']['strike']=dict(value=4200,source='issuer',at='original')
        out=self.apply(p)
        self.assertEqual(out['conditions']['strike'],p['conditions']['strike'])
        self.assertIn('strike',out['comdirectFieldsBackup']['conflicts'])
        self.assertNotIn('ratio',p['conditions'])

    def test_direction_currency_underlying_conflict_blocks_replacement(self):
        for key,value in [('direction','SHORT'),('currency','CHF'),('underlying','Gold Future 12/2026 (COMEX) USD')]:
            p=self.primary(); p['metadata'][key]=value
            out=self.apply(p)
            self.assertEqual(out['conditions'],{})
            self.assertEqual(out['comdirectFieldsBackup']['state'],'conflict')

    def test_metadata_value_is_not_overridden_by_missing_condition(self):
        p=self.primary(); p['metadata']['ko']=4200
        out=self.apply(p)
        self.assertNotIn('ko',out['conditions'])
        self.assertIn('ko',out['comdirectFieldsBackup']['conflicts'])

    def test_undated_metrics_not_promoted_to_issuer_leverage(self):
        fields=self.parse(HTML.replace('Kennzahlen Knock','Kennzahlen Hebel 12,34 Abstand zum Knock Out 1,39 % (57,89) Knock'))
        out=self.apply(fields=fields)
        self.assertEqual(fields['observations']['leverage']['value'],12.34)
        self.assertFalse(fields['observations']['leverage']['conditionVerified'])
        self.assertNotIn('leverage',out['conditions'])
        self.assertNotIn('koDistancePct',out['conditions'])
        self.assertIn('financingCosts',fields['missing'])

    def test_wrong_identity_and_factor_rejected(self):
        for html in (HTML.replace(ISIN,'DE000FG8NHQ3'),HTML.replace('Hebel-Bull-Zertifi..','Faktor-Zertifikat')):
            with self.assertRaises(ValueError):self.parse(html)

    def test_inactive_secondary_cannot_promote_product(self):
        p=self.primary(); p.update(found=True,eligible=True)
        fields=self.parse(HTML.replace('erreicht Nein','erreicht Ja'))
        out=self.apply(p,fields)
        self.assertFalse(out['eligible'])
        self.assertEqual(out['comdirectFieldsBackup']['state'],'inactive')

    def test_missing_quote_does_not_discard_terms(self):
        html=HTML.replace('data-label="LiveTrading"','data-label="Other"')
        with patch.object(q,'open_public_page') as network:
            r=network.return_value.__enter__.return_value
            r.url=f.ORIGIN+'inf/zertifikate/'+ISIN
            r.read.return_value=html.encode()
            q._refresh(ISIN)
        evidence=q._CACHE.pop(ISIN)[1]
        self.assertEqual(evidence['fields']['observations']['ratio']['value'],.1)
        self.assertEqual(evidence['quoteState'],'unavailable')


if __name__=='__main__':unittest.main()

class PrintedPrecisionTests(ComdirectFieldsTests):
    def test_rounding_preserves_exact_issuer_terms(self):
        fields=self.parse();p=self.primary()
        p['metadata'].update(simpleTurbo=True,classificationId=47)
        p['conditions']['type']={'value':'BEST Turbo-Optionsscheine (Open-End)'}
        for key in ('ko','strike'):
            fields['observations'][key].update(value=4221.2948,displayDecimals=4)
            p['conditions'][key]={'value':4221.294764,'source':'issuer','at':'original'}
        out=self.apply(p,fields)
        self.assertEqual(out['comdirectFieldsBackup']['conflicts'],[])
        self.assertEqual(out['conditions']['ko'],p['conditions']['ko'])
        fields['observations']['ko']['value']=4221.295
        self.assertIn('ko',self.apply(p,fields)['comdirectFieldsBackup']['conflicts'])
        fields['observations']['ko'].pop('displayDecimals')
        self.assertIn('ko',self.apply(p,fields)['comdirectFieldsBackup']['conflicts'])

    def test_precision_is_observed_not_assumed(self):
        self.assertEqual(self.parse()['observations']['ko']['displayDecimals'],4)
        self.assertFalse(f.display_equivalent('ko',4221.294764,{'value':4221,'displayDecimals':0}))
