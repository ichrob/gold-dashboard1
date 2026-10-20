import copy
import unittest
from unittest.mock import Mock,patch
import decision_evidence as evidence
import decision_audit as audit
import audit_history

class DecisionEvidenceTests(unittest.TestCase):
    def market(self):
        return dict(ready=True,priceFresh=True,analysisBarAt=1800000000000-300000,
            dataAt=1800000000000,price=4000,direction='NEUTRAL',ruleVersion=audit.RULE_VERSION,
            analysisSnapshot=dict(timeframe='15m',R=56,at=12,e20=4001,e50=3998,e200=3900,
                macd=2,sig=1.5,hist=.5,adx=24,account='never-store'),
            entryTimingGate=dict(allowed=False,reason='Keine bestätigte Einstiegsrichtung',token='never-store'),
            session=dict(entryAllowed=True,reason='Zeitfenster'),dmi=dict(available=True,direction='LONG',mode='shadow'))

    def test_original_values_are_frozen_without_mutating_source(self):
        market=self.market();original=copy.deepcopy(market);result=evidence.capture(market)
        self.assertEqual(result['indicators']['ema20'],4001)
        self.assertEqual(result['indicators']['rsi'],56)
        self.assertEqual(result['indicators']['atr'],12)
        self.assertEqual(result['indicators']['signal'],1.5)
        self.assertFalse(result['entryTiming']['allowed'])
        self.assertNotIn('never-store',str(result))
        market['analysisSnapshot']['e20']=999
        self.assertEqual(result['indicators']['ema20'],4001)
        self.assertEqual(original['analysisSnapshot']['e20'],4001)

    def test_missing_and_invalid_values_are_not_reconstructed(self):
        result=evidence.capture(dict(analysisSnapshot=dict(e20=float('nan'),R=True)))
        for field in ('ema20','ema50','rsi','barAt'):self.assertIsNone(result['indicators'][field])
        self.assertIsNone(result['ready'])
        self.assertIsNone(evidence.freeze(dict(version='unknown')))
        self.assertIsNone(audit.normalize(dict(direction='NEUTRAL',barAt=1),2)[1]['decisionContext'])

    def test_changed_evidence_is_a_new_revision_but_refresh_is_idempotent(self):
        market=self.market();context=evidence.capture(market)
        payload=dict(direction='NEUTRAL',barAt=market['analysisBarAt'],priceAt=market['dataAt'],price=4000,
            decisionContext=context)
        first,stored=audit.normalize(payload,market['dataAt'])
        self.assertEqual(first,audit.normalize(payload,market['dataAt']+1000)[0])
        market['analysisSnapshot']['e20']=4002
        self.assertNotEqual(first,audit.normalize(dict(payload,decisionContext=evidence.capture(market)),market['dataAt'])[0])
        self.assertEqual(stored['decisionContext']['indicators']['ema20'],4001)
        self.assertNotIn('approved',stored['decisionContext'])

    def test_background_writes_context_and_history_exposes_it(self):
        from datetime import datetime,timezone
        import push_server
        market=self.market()
        with patch('push_server.time.time',return_value=1800000000),patch.object(audit,'write') as write:
            self.assertTrue(push_server.record_market_observation(Mock(),market))
        payload=write.call_args.args[1]
        self.assertEqual(payload['decisionContext'],evidence.capture(market))
        _,stored=audit.normalize(payload,market['dataAt'])
        row=audit_history.compact(('id',datetime.now(timezone.utc),stored,{}))
        self.assertEqual(row['decisionContext']['entryTiming']['reason'],'Keine bestätigte Einstiegsrichtung')
