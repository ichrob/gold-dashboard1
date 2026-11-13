import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
import finanzen_terms as f
import handset_contract_model as h

ISIN='DE000FG8NHQ3'
NOW=datetime(2026,11,13,12,tzinfo=timezone.utc)
PAGE=Path(__file__).with_name('test_fixtures').joinpath('finanzen_fg8nhq_terms.txt').read_text()


def record(side='SHORT'):
    page=PAGE.replace('Typ Bear','Typ Bull') if side=='LONG' else PAGE
    backup=dict(state='available',**f.parse_page(page,ISIN,NOW))
    source='https://www.sg-zertifikate.ch/product-details/'+ISIN.lower()
    q=dict(isin=ISIN,productVerified=True,importActive=True,eligible=False,found=False,
        metadata=dict(status=1,currency='CHF',issuerExchangeCode='CBSW',classificationId=43,
            simpleTurbo=True,quantoState='unknown',termsFixed=True,underlyingType='SPOT',
            underlying='XAU/USD',direction=side,ratio=.1,strike=4400.,ko=4400.),
        conditions=dict(maturity=dict(value='19.03.2027')))
    for key in ('ko','strike'):
        q['conditions'][key]=dict(value=4400.,source=source,conditionVerified=True,
            fixed=True,validUntil='2027-03-19',at=None)
    with patch.object(f,'fetch',return_value=backup):
        return f.apply(q,ISIN)


class ContractModel(unittest.TestCase):
    def test_matched_explicit_evidence_long_short_preserves_originals(self):
        for side in ('LONG','SHORT'):
            q=record(side);before=copy.deepcopy(q)
            out=h.attach(q,NOW)
            self.assertEqual(q,before)
            self.assertEqual(out['productModel']['direction'],side)
            self.assertTrue(out['productModel']['verifiedSimpleTurbo'])
            self.assertEqual(out['productModel']['scope'],'handset-comparison')
            self.assertFalse(out['eligible'])
            self.assertNotIn('calculatedProduct',out)
            self.assertIsNone(out['conditions']['ko']['at'])

    def test_missing_conflicting_stale_or_inactive_evidence_never_forms_model(self):
        mutations=[lambda q:q.update(sourceFailure=True),lambda q:q.update(productVerified=False),
            lambda q:q.update(quoteFailureCode='INVALID_RESPONSE'),
            lambda q:q['metadata'].update(status=2),lambda q:q['metadata'].update(quantoState='quanto'),
            lambda q:q['metadata'].update(classificationId=45),lambda q:q['metadata'].update(currency='EUR'),
            lambda q:q['metadata'].update(underlyingType='FUTURE'),lambda q:q['metadata'].update(ratio=.2),
            lambda q:q['conditions']['ko'].update(fixed=False),lambda q:q['conditions']['ko'].update(conditionVerified=False),
            lambda q:q['conditions']['ko'].update(conflict=True),lambda q:q['conditions']['ko'].update(value=4401),
            lambda q:q['conditions']['ko'].update(revoked=True),
            lambda q:q['conditions']['ko'].update(source='wrong'),lambda q:q['conditions']['ko'].update(validUntil='2026-11-12'),
            lambda q:q['termsBackup'].update(state='unavailable')]
        for key,value in [('quanto',True),('quanto',0),('quanto',None),('isin','wrong'),
            ('revoked',True),('conflict',True),('ocrCorrection',True),
            ('source','wrong'),('direction','LONG'),('ratio',.2),('ko',4401),
            ('reviewedAt',(NOW-timedelta(hours=9)).isoformat()),
            ('reviewedAt',(NOW+timedelta(seconds=1)).isoformat()),('reviewedAt','undated')]:
            mutations.append(lambda q,k=key,v=value:q['termsBackup']['currencyTreatment'].update({k:v}))
        for change in mutations:
            q=record();change(q)
            self.assertNotIn('productModel',h.attach(q,NOW))
        for clock in (NOW.replace(hour=23),NOW+timedelta(days=1)):
            self.assertNotIn('productModel',h.attach(record(),clock))

    def test_existing_model_is_never_replaced(self):
        q=record();q['productModel']={'existing':True}
        self.assertIs(h.attach(q,NOW),q)

    def test_parser_retains_only_explicit_currency_treatment(self):
        for label,value in [('Nein',False),('Ja',True)]:
            result=f.parse_page(PAGE.replace('Währungssicherheit Nein','Währungssicherheit '+label),ISIN,NOW)
            self.assertIs(result['currencyTreatment']['quanto'],value)
        result=f.parse_page(PAGE.replace('Währungssicherheit Nein','Währungssicherheit --'),ISIN,NOW)
        self.assertIsNone(result['currencyTreatment'])
        self.assertNotIn('ratio',f.parse_page(PAGE,ISIN,NOW)['conditions'])
