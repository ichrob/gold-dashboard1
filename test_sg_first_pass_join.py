"""Fail-closed regression for first-pass SG identity and market-data joins."""
import copy
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import sg_direct as sg
import product_quotes as q
import comdirect_quotes as comdirect

LONG = 'DE000FC1CHB7'
SHORT = 'DE000FG4JXV7'

def fixture(isin=LONG):
    at=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat()
    chart=dict(pointAt=at, bid=10.37, ask=10.38, currency='EUR')
    side='LONG' if isin==LONG else 'SHORT'
    meta=dict(status=1, issuerExchangeCode='CBDE', currency='EUR',
              direction=side, underlying='XAU/USD', underlyingType='SPOT',
              ko=4037.98, strike=4037.98, ratio=.1,
              simpleTurbo=True, simpleNonQuantoTurbo=True, termsDated=False)
    verified=dict(isin=isin,productVerified=True,found=False,eligible=False,
                  fresh=False,metadata=meta,chartEvidence=chart,importActive=True,
                  conditions={'ko':dict(value=4037.98,at=None,source='SG',conditionVerified=False)},
                  observedTerms=dict(ko=4037.98),termsCheckedAt=at,
                  issuerLeverageReference=dict(value=35.14,sourceAt=None),
                  sharedTimeContext=dict(isin=isin,at=at),
                  sharedValueObservations={'Geld':dict(value=10.37,contextAt=at)})
    partial=dict(isin=isin,productVerified=True,found=False,eligible=False,
                 fresh=False,source='SG · datierter Chartkurs',metadata=dict(status=1,ratio=.1),
                 chartEvidence=copy.deepcopy(chart),analysisQuote=dict(isin=isin,
                 bid=10.37,ask=10.38,bidAt=at,askAt=at,
                 priceKind='issuer-chart',isExecutableQuote=False))
    return verified,partial

class FirstPassJoinTests(unittest.TestCase):
    def setUp(self):
        self.verified,self.partial=fixture()
    def restore(self, partial=None, verified=None, age=0, isin=LONG):
        val=self.verified if verified is None else verified
        with patch.object(sg,'_CACHE',{isin:(time.monotonic()-age,copy.deepcopy(val))}), \
             patch.object(q,'get_sg_quote',side_effect=AssertionError('network source not allowed')):
            return q._restore_exact_sg_metadata(copy.deepcopy(self.partial if partial is None else partial),isin)

    def test_restore_long_exact_source_and_preserve_original_times(self):
        r=self.restore()
        self.assertTrue(r['sgCachedIdentityRestored'])
        self.assertEqual(r['metadata']['direction'],'LONG')
        self.assertEqual(r['metadata']['issuerExchangeCode'],'CBDE')
        self.assertEqual(r['chartEvidence'],self.partial['chartEvidence'])
        self.assertIsNone(r['issuerLeverageReference']['sourceAt'])
        self.assertEqual(r['sharedTimeContext']['at'],self.verified['sharedTimeContext']['at'])
        self.assertEqual(r['conditions']['ko']['at'],None)
        self.assertEqual(r['termsCheckedAt'],self.verified['termsCheckedAt'])
        self.assertFalse(r['found']);self.assertFalse(r['eligible']);self.assertFalse(r['fresh'])

    def test_restore_short_with_matching_product(self):
        v,p=fixture(SHORT)
        r=self.restore(partial=p,verified=v,isin=SHORT)
        self.assertEqual(r['metadata']['direction'],'SHORT')
        self.assertFalse(r['eligible'])

    def test_comdirect_joins_after_restore_without_promoting_execution(self):
        now=datetime.now(timezone.utc)
        at=(now-timedelta(seconds=15)).isoformat()
        observation=dict(state='observed',quote=dict(isin=LONG,currency='EUR',
            bid=10.34,ask=10.36,bidAt=at,askAt=at,quoteAt=at,
            source='comdirect · SG LiveTrading',venue='LT Societe Generale',
            priceKind='market-observation',isExecutableQuote=False,
            degiroExecutable=False))
        restored=self.restore()
        with patch.object(comdirect,'get_observation',return_value=observation):
            out=comdirect.apply(restored,LONG,now)
        self.assertEqual(out['comdirectQuoteBackup']['state'],'current')
        self.assertEqual(out['secondaryQuote']['source'],'comdirect · SG LiveTrading')
        self.assertEqual(out['secondaryQuote']['bidAt'],at)
        self.assertEqual(out['secondaryQuote']['askAt'],at)
        self.assertFalse(out['found']);self.assertFalse(out['eligible'])
        self.assertFalse(out['secondaryQuote']['degiroExecutable'])

    def test_mismatch_or_disabled_fails_closed(self):
        for patch_value in (
            {'isin':SHORT},{'sourceDisabled':True},{'sourceFailure':True},
            {'quoteFailureCode':'FAILED'},{'found':True},{'metadata':{'status':2}},
            {'metadata':{'status':1,'direction':'SHORT'}},
            {'metadata':{'status':1,'ko':4000}},
            {'metadata':{'status':1,'issuerExchangeCode':'CBSW'}},
            {'chartEvidence':dict(self.partial['chartEvidence'],pointAt='2020-01-01T00:00:00Z')},
            {'chartEvidence':dict(self.partial['chartEvidence'],ask=11.2)},
            {'chartEvidence':dict(self.partial['chartEvidence'],currency='CHF')},
        ):
            with self.subTest(change=patch_value):
                p=copy.deepcopy(self.partial)
                p.update(patch_value)
                self.assertEqual(self.restore(partial=p),p)
        self.assertEqual(self.restore(age=31),self.partial)

    def test_wrong_reference_and_conflicting_issuer_is_rejected(self):
        for change in (
            {'isin':SHORT},
            {'sourceFailure':True},
            {'quoteFailureCode':'SG_SOURCE_UNAVAILABLE'},
            {'productVerified':False},
            {'metadata':dict(self.verified['metadata'],status=2)},
            {'metadata':dict(self.verified['metadata'],currency='CHF')},
            {'chartEvidence':dict(self.verified['chartEvidence'],bid=10.5)},
            {'chartEvidence':dict(self.verified['chartEvidence'],pointAt='2020-01-01T00:00:00Z')},
        ):
            with self.subTest(change=change):
                v=copy.deepcopy(self.verified);v.update(change)
                self.assertEqual(self.restore(verified=v),self.partial)

if __name__ == '__main__':
    unittest.main()
