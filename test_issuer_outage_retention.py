"""Regression: provider outages never turn receipt time into an issuer quote clock."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sg_direct
import comdirect_quotes


class SGOutageRetentionTests(unittest.TestCase):
    def setUp(self):
        self.old_time = '2026-10-15T06:20:00+00:00'
        self.isin = 'DE000FG8NHQ3'
        self.old = dict(isin=self.isin, productVerified=True, importActive=True,
            checkedAt=self.old_time, termsCheckedAt=self.old_time,
            source='Société Générale · Direktimport',
            metadata=dict(status=1, currency='CHF', underlying='XAU/USD',
                          direction='SHORT', ko=4200, ratio=0.1,
                          issuerExchangeCode='CBSW'),
            conditions=dict(ko=dict(value=4200), strike=dict(value=4210),
                            ratio=dict(value=0.1)),
            chartEvidence=dict(bid=2.04, ask=2.08, currency='CHF',
                               pointAt=self.old_time),
            sharedTimeContext=dict(isin=self.isin, at=self.old_time),
            issuerLeverageReference=dict(value=34.5, sharedContextAt=self.old_time))
        self.failed = dict(isin=self.isin,
            checkedAt='2026-10-15T06:20:35+00:00', sourceFailure=True,
            quoteFailureCode='SG_SOURCE_UNAVAILABLE',
            reason='SG datierte Kurse: Zeitlimit erreicht')

    def test_outage_keeps_original_market_and_term_clocks(self):
        retained = sg_direct.retain_last_verified_observation(
            self.old, self.failed, 'dated-quotes')
        self.assertEqual(retained['chartEvidence']['pointAt'], self.old_time)
        self.assertEqual(retained['termsCheckedAt'], self.old_time)
        self.assertEqual(retained['sharedTimeContext']['at'], self.old_time)
        self.assertEqual(retained['checkedAt'], self.failed['checkedAt'])
        self.assertTrue(retained['sourceFailure'])
        self.assertFalse(retained.get('eligible', False))
        self.assertIn('ORIGINAL-Kurszeit', retained['reason'])
        self.assertEqual(self.old['chartEvidence']['pointAt'], self.old_time)
        # The display must not overwrite the error with the success message.
        with patch.object(sg_direct, 'datetime') as clock:
            clock.now.return_value = datetime.fromisoformat(
                '2026-10-15T06:20:35+00:00')
            refreshed = sg_direct.refresh_evidence(retained)
        self.assertIn('Zeitlimit', refreshed['reason'])
        self.assertEqual(refreshed['chartEvidence']['pointAt'], self.old_time)

    def test_new_terminal_status_must_not_reuse_old_observation(self):
        failed = dict(self.failed, productVerified=True,
                      metadata=dict(self.old['metadata'], status=2))
        self.assertIs(sg_direct.retain_last_verified_observation(
            self.old, failed, 'dated-quotes'), failed)

    def test_changed_contract_or_terms_must_not_reuse_old_price(self):
        for difference in (dict(metadata=dict(self.old['metadata'], ko=4250)),
                           dict(conditions=dict(ko=dict(value=4250)))):
            failed = dict(self.failed, productVerified=True,
                          metadata=copy.deepcopy(self.old['metadata']), **difference)
            self.assertIs(sg_direct.retain_last_verified_observation(
                self.old, failed, 'dated-quotes'), failed)

    def test_no_preexisting_verified_chart_returns_failure(self):
        prior = dict(self.old, chartEvidence=None)
        self.assertIs(sg_direct.retain_last_verified_observation(
            prior, self.failed, 'identity'), self.failed)


class ComdirectOutageRetentionTests(unittest.TestCase):
    def setUp(self):
        self.isin = 'DE000FG7N6Z2'
        self.at = '2026-10-15T06:20:00+02:00'
        self.quote = dict(isin=self.isin, quoteAt=self.at,
                          bidAt=self.at, askAt=self.at, bid=5.43, ask=5.44,
                          currency='EUR', priceKind='market-observation',
                          source='comdirect · SG LiveTrading',
                          venue='LT Societe Generale',
                          isExecutableQuote=False, degiroExecutable=False)
        self.previous = dict(state='observed', quote=self.quote)

    def test_failed_refresh_preserves_old_clock_and_unavailable_state(self):
        with patch.dict(comdirect_quotes._CACHE,
                        {self.isin: (0, self.previous)}, clear=True), \
             patch.object(comdirect_quotes, 'open_public_page',
                          side_effect=OSError('source timeout')):
            comdirect_quotes._refresh(self.isin)
            entry = comdirect_quotes._CACHE[self.isin][1]
        self.assertEqual(entry['state'], 'unavailable')
        self.assertTrue(entry['retainedAfterFailure'])
        self.assertEqual(entry['quote']['bidAt'], self.at)
        self.assertNotIn('fields', entry)
        self.assertFalse(entry['quote']['degiroExecutable'])

    def test_prior_observation_for_other_isin_not_carried(self):
        previous = dict(self.previous, quote=dict(self.quote, isin='DE000FG8NHQ3'))
        with patch.dict(comdirect_quotes._CACHE,
                        {self.isin: (0, previous)}, clear=True), \
             patch.object(comdirect_quotes, 'open_public_page',
                          side_effect=OSError('source timeout')):
            comdirect_quotes._refresh(self.isin)
            entry = comdirect_quotes._CACHE[self.isin][1]
        self.assertNotIn('quote', entry)


if __name__ == '__main__':
    unittest.main()
