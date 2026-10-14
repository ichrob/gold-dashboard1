import copy
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import swissquote_quotes as q


class SwissquoteTests(unittest.TestCase):
    def setUp(self):
        self.isin = 'DE000FG14AV8'
        self.payload = json.loads(Path('test_fixtures/swissquote_long.json').read_text())
        self.now = datetime.fromisoformat('2026-10-14T18:54:02+02:00')
        self.primary = dict(isin=self.isin, productVerified=True, found=False,
            eligible=False, fresh=False, direction='LONG', currency='CHF',
            metadata=dict(status=1, currency='CHF', issuerExchangeCode='CBSW', direction='LONG'))

    def apply(self, payload=None, now=None, primary=None):
        evidence = q.parse_payload(payload or self.payload, self.isin, self.now)
        with patch.object(q, 'get_observation', return_value=evidence):
            return q.apply(primary or self.primary, self.isin, now or self.now)

    def test_live_fixtures_native_fields_and_clocks(self):
        for name, isin in [('long', self.isin), ('short', 'DE000FG8NHQ3')]:
            payload = json.loads(Path('test_fixtures/swissquote_'+name+'.json').read_text())
            e = q.parse_payload(payload, isin, self.now)
            self.assertEqual(e['fields']['ratio']['value'], .1)
            self.assertEqual(e['quote']['currency'], 'CHF')
            self.assertEqual(e['quote']['bidAt'], payload['fullQuoteData']['quote']['bidPrice']['timestamp'])
            self.assertIsNone(e['fields']['ko']['sourceAt'])
            self.assertTrue(e['fields']['ko']['validityUnconfirmed'])
            self.assertEqual(e['leverageTimeState'], 'not-supplied')

    def test_audit_uses_quote_but_does_not_invent_leverage_or_execution(self):
        from degiro_product_audit import examine
        out = self.apply()
        audit = examine(dict(isin=self.isin, direction='LONG'), out, self.now.timestamp()*1000)
        for missing in ('quote', 'quote-time', 'market-status'):
            self.assertNotIn(missing, audit['missing'])
        for missing in ('leverage', 'leverage-time', 'ko-time'):
            self.assertIn(missing, audit['missing'])
        self.assertEqual(audit['dataQuoteSource'], q.SOURCE)
        self.assertEqual(audit['sourceObservations'][0]['currency'], 'CHF')
        self.assertEqual(out['analysisQuote']['currency'], 'CHF')
        for flag in ('eligible', 'found', 'fresh'):
            self.assertFalse(out[flag])
        self.assertNotIn('thirdQuote', self.primary)

    def test_both_independent_clocks_required(self):
        for field in ('bidPrice', 'askPrice'):
            for timestamp in (None, '2026-10-14T18:54:01', '2026-10-14T18:50:00+02:00', '2026-10-14T19:00:00+02:00'):
                p = copy.deepcopy(self.payload)
                p['fullQuoteData']['quote'][field]['timestamp'] = timestamp
                self.assertIsNone(q.current_pair(self.apply(p), self.now))
        p = copy.deepcopy(self.payload)
        p['fullQuoteData']['quote']['bidPrice']['timestamp'] = '2026-10-14T18:54:00+02:00'
        self.assertIsNotNone(q.current_pair(self.apply(p), self.now))

    def test_identity_delay_closed_crossed_and_disabled(self):
        for key, value in [('issuerName','Other'), ('optionType','PUT'), ('eusipaCode','2100'),
                           ('stockKey',dict(isin=self.isin, exchangeId=1, currency='EUR'))]:
            p = copy.deepcopy(self.payload); p['fullQuoteData'][key] = value
            with self.assertRaises(ValueError): q.parse_payload(p, self.isin)
        for key, value in [('serviceLevel','DELAYED'), ('bidPrice', dict(amount=99, status='AVAILABLE'))]:
            p = copy.deepcopy(self.payload);p['fullQuoteData']['quote'][key] = value
            self.assertIsNone(q.current_pair(self.apply(p), self.now))
        p = copy.deepcopy(self.payload);p['fullQuoteData']['marketStatus'] = 'MARKET_CLOSED'
        self.assertIsNone(q.current_pair(self.apply(p), self.now))
        for changes in (dict(sourceDisabled=True), dict(productVerified=False),
                        dict(metadata=dict(status=2, currency='CHF', issuerExchangeCode='CBSW'))):
            self.assertNotIn('thirdQuote', self.apply(primary=dict(self.primary, **changes)))

    def test_expiry_never_relabels_retrieval_as_quote_time(self):
        out = self.apply(now=self.now+timedelta(seconds=91))
        self.assertNotIn('analysisQuote', out)
        self.assertEqual(out['thirdQuote']['quoteAt'], '2026-10-14T18:54:01+02:00')
        self.assertIsNone(q.current_pair(out, self.now+timedelta(seconds=91)))

    def test_keeps_newer_analysis_and_secondary(self):
        primary = dict(self.primary, analysisQuote=dict(askAt=self.now.isoformat(), currency='EUR'),
                       secondaryQuote=dict(source='other'))
        out = self.apply(primary=primary)
        self.assertEqual(out['analysisQuote'], primary['analysisQuote'])
        self.assertEqual(out['secondaryQuote'], primary['secondaryQuote'])

    def test_unsupported_does_not_start_network(self):
        with patch.object(q._POOL, 'submit') as submit:
            self.assertEqual(q.get_observation('DE000PJ9NB98')['state'], 'unsupported')
            submit.assert_not_called()

if __name__ == '__main__': unittest.main()
