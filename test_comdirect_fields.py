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

    def test_sg_mini_type_alias_preserves_original_and_requires_class(self):
        p=self.primary()
        p['metadata'].update(simpleTurbo=True,classificationId=45)
        original=dict(value='Unlimited Turbo-Optionsscheine (Mini)',source='issuer',at='original')
        p['conditions']['type']=original
        out=self.apply(p)
        self.assertNotIn('type',out['comdirectFieldsBackup']['conflicts'])
        self.assertEqual(out['conditions']['type'],original)
        self.assertFalse(out['eligible'])
        for changes in [dict(classificationId=47),dict(simpleTurbo=False)]:
            bad=copy.deepcopy(p);bad['metadata'].update(changes)
            self.assertIn('type',self.apply(bad)['comdirectFieldsBackup']['conflicts'])
        bad=copy.deepcopy(p);bad['conditions']['type']['value']='Faktor-Zertifikat'
        self.assertIn('type',self.apply(bad)['comdirectFieldsBackup']['conflicts'])

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
    def test_dated_issuer_decision_preserves_raw_difference_and_all_safety_flags(self):
        p=self.primary()
        p['metadata']['strike']=4200
        p['conditions']['strike']=dict(value=4200,source='https://www.sg-zertifikate.de/product-details/'+ISIN.lower(),
            conditionVerified=True,dateText='14.10.2026',sourceField='StrikeBarrierUpdateTime',
            sourceTimeRaw='2026-10-14T01:00:00',reviewedAt=NOW.isoformat())
        fields=self.parse()
        with patch.object(q,'get_observation',return_value=dict(state='observed',fields=fields)):
            out=f.apply(p,ISIN,NOW)
        report=out['comdirectFieldsBackup']
        self.assertEqual(report['sourceDecisions']['strike']['state'],'dated-issuer-selected')
        self.assertEqual(report['unresolvedConflicts'],[])
        self.assertIn('strike',report['conflicts'])
        self.assertEqual(report['state'],'conflict')
        self.assertEqual(out['conditions']['strike'],p['conditions']['strike'])
        self.assertFalse(out['eligible']);self.assertFalse(out['found'])
        # No time zone is inferred from an issuer's local source time.
        self.assertNotIn('at',out['conditions']['strike'])
        for changes in (dict(dateText='13.10.2026'),dict(sourceTimeRaw='2026-10-13T01:00:00'),
                        dict(conditionVerified=False),dict(revoked=True),dict(source='https://evil.example/'+ISIN),
                        dict(reviewedAt='2026-10-13T01:00:00+00:00'),dict(reviewedAt='2026-10-15T01:00:00+00:00')):
            bad=copy.deepcopy(p);bad['conditions']['strike'].update(changes)
            with patch.object(q,'get_observation',return_value=dict(state='observed',fields=fields)):
                r=f.apply(bad,ISIN,NOW)['comdirectFieldsBackup']
            self.assertIn('strike',r['unresolvedConflicts'])
        dated=copy.deepcopy(fields)
        dated['observations']['strike']['dateText']='14.10.2026'
        with patch.object(q,'get_observation',return_value=dict(state='observed',fields=dated)):
            self.assertIn('strike',f.apply(p,ISIN,NOW)['comdirectFieldsBackup']['unresolvedConflicts'])

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

    def test_two_decimal_issuer_strike_matches_four_decimal_portal_without_override(self):
        # DE000SQ02JQ6: list/issuer print 2117.58; comdirect reads
        # 2117.5757. Both round to the same two-decimal printed BP.
        fields = self.parse()
        fields['observations']['strike'].update(value=2117.5757, displayDecimals=4)
        primary = self.primary()
        primary['metadata']['strike'] = 2117.58
        primary['conditions']['strike'] = dict(
            value=2117.58, source='issuer', at='original',
            conditionVerified=True)
        out = self.apply(primary, fields)
        self.assertNotIn('strike', out['comdirectFieldsBackup']['conflicts'])
        self.assertEqual(out['conditions']['strike'], primary['conditions']['strike'])
        self.assertEqual(out['metadata']['strike'], 2117.58)
        self.assertFalse(out['eligible'], 'rounded agreement does not approve trading')

        for other in (2117.5657, 2117.5857, 2117.6757):
            changed = copy.deepcopy(fields)
            changed['observations']['strike']['value'] = other
            bad = self.apply(primary, changed)
            self.assertIn('strike', bad['comdirectFieldsBackup']['conflicts'])
        bad_precision = copy.deepcopy(primary)
        bad_precision['metadata']['strike'] = 2117.5802
        bad_precision['conditions']['strike']['value'] = 2117.5802
        self.assertIn('strike', self.apply(bad_precision, fields)['comdirectFieldsBackup']['conflicts'])
        unconfirmed = copy.deepcopy(fields)
        unconfirmed['observations']['strike'].pop('displayDecimals')
        self.assertIn('strike', self.apply(primary, unconfirmed)['comdirectFieldsBackup']['conflicts'])
        self.assertFalse(f.display_equivalent(
            'ko', 2117.58, dict(value=2117.5757, displayDecimals=4)),
            'No general KO-barrier rounding relaxation')

