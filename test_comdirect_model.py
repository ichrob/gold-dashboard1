import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
import comdirect_fields
import leverage_backup as b
from test_comdirect_fields import HTML, ISIN, NOW

class ModelTests(unittest.TestCase):
    def quote(self):
        fields=comdirect_fields.parse_page(HTML,ISIN,NOW)
        obs=fields['observations']
        self.assertIs(obs['quanto']['value'],False)
        q=dict(isin=ISIN,productVerified=True,found=False,eligible=False,
          metadata=dict(status=1,simpleTurbo=True,simpleNonQuantoTurbo=False,
          quantoState='unknown',underlyingType='SPOT',underlying='XAU/USD',
          currency='EUR',direction='LONG',ratio=.1),
          conditions={'type':dict(value='Unlimited Long')})
        with patch('comdirect_quotes.get_observation',return_value=dict(state='observed',fields=fields)):
            return comdirect_fields.apply(q,ISIN)
    def test_matching_model_without_trade_approval(self):
        q=self.quote();before=copy.deepcopy(q)
        self.assertEqual(q['comdirectFieldsBackup']['conflicts'],[])
        out=b.reconcile_model(q,NOW)
        self.assertTrue(out['metadata']['simpleNonQuantoTurbo'])
        self.assertFalse(out['eligible']);self.assertFalse(out['found'])
        self.assertEqual(q,before)
        self.assertFalse(b.reconcile_model(out,NOW+timedelta(hours=9))['metadata']['simpleNonQuantoTurbo'])
    def test_bad_proof_stays_unknown(self):
        for mutate in [
          lambda q:q['comdirectFieldsBackup'].update(isin='wrong'),
          lambda q:q['comdirectFieldsBackup'].update(state='conflict'),
          lambda q:q['comdirectFieldsBackup'].update(conflicts=['ratio']),
          lambda q:q['comdirectFieldsBackup']['observations']['quanto'].update(value=True),
          lambda q:q['comdirectFieldsBackup']['observations']['quanto'].update(value=0),
          lambda q:q['comdirectFieldsBackup']['observations']['quanto'].update(revoked=True),
          lambda q:q['comdirectFieldsBackup']['observations']['ratio'].update(value=.2),
          lambda q:q['comdirectFieldsBackup']['observations']['direction'].update(value='SHORT'),
          lambda q:q['conditions']['quanto'].update(value=True),
          lambda q:q['metadata'].update(quantoState='quanto'),
          lambda q:q['metadata'].update(simpleTurbo=False),
        ]:
            q=self.quote();mutate(q)
            self.assertFalse(b.reconcile_model(q,NOW)['metadata']['simpleNonQuantoTurbo'])
    def test_real_calculation_and_audit_clock(self):
        q=b.reconcile_model(self.quote(),NOW)
        at=NOW.isoformat()
        q.update(analysisQuote=dict(bid=3.99,ask=4,askAt=at,bidAt=at,currency='EUR',priceKind='market-observation'))
        basis=dict(price=4000,at=at,underlying='XAU/USD',source='test')
        fx=dict(result='success',base='USD',rates=dict(EUR=.9),data_updated_at=at,effective_at=dict(EUR=at),source='live',sources=dict(EUR='live'),market_session='open')
        q['leverageCalculation']=b.calculate(q,basis,fx,NOW)
        self.assertEqual(b.current_evidence(q,NOW)['value'],90)
        self.assertIsNone(b.current_evidence(q,NOW+timedelta(minutes=6)))
