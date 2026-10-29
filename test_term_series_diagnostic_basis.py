"""Preserve the existing series policy and the absent original issuer date."""
import ast
import copy
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import bob_diagnostics as diagnostics
from term_series import observed_condition


class SeriesDiagnosticBasisTests(unittest.TestCase):
    now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc).timestamp() * 1000

    def setUp(self):
        # Run the actual audit helpers without unrelated network/provider imports.
        names = {'_positive', '_time_ms', '_recent', '_condition_value',
                 '_dated_barrier', '_term_time_evidence'}
        tree = ast.parse(Path(__file__).with_name('degiro_product_audit.py').read_text())
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.ns = dict(datetime=datetime, timezone=timezone, math=math,
                       ZURICH=ZoneInfo('Europe/Zurich'), BARRIER_MAX_MS=8*3600000)
        exec(compile(ast.Module(body=body, type_ignores=[]), '<audit>', 'exec'), self.ns)
        stamp = datetime.fromtimestamp(self.now/1000, timezone.utc).isoformat()
        self.quote = dict(isin='SYNTHETIC', productVerified=True,
                          metadata={'ko': 4000}, termsCheckedAt=stamp,
                          conditions={k: observed_condition(4000, 'issuer-source', 'SYNTHETIC', stamp)
                                      for k in ('ko', 'strike')})

    def report(self, quote=None, now=None):
        quote = quote or self.quote
        now = self.now if now is None else now
        terms = {k: self.ns['_term_time_evidence'](quote, k, now) for k in ('ko', 'strike')}
        projected = diagnostics.product_snapshot({'items': [{'timeEvidence': {'terms': terms}}]})
        with patch('bob_diagnostics.time.time', return_value=now/1000):
            result = diagnostics.summary({'products': projected})
        return projected, result

    def test_accepted_series_survives_projection_without_issuer_date(self):
        original = copy.deepcopy(self.quote)
        projected, result = self.report()
        for term in projected['items'][0]['timeEvidence']['terms'].values():
            self.assertTrue(term['policyAccepted'])
            self.assertFalse(term['conditionVerified'])
            self.assertTrue(term['validityUnconfirmed'])
            self.assertIsNone(term['at'])
            self.assertIsNone(term['dateText'])
        self.assertEqual(result['assessment'], 'observed-only')
        self.assertTrue(all(x['severity'] == 'info' for x in result['attention']))
        self.assertEqual(self.quote, original)

    def test_bad_series_and_expiry_still_warn(self):
        for mutation in ('missing', 'wrong-isin', 'wrong-source', 'revoked', 'unverified'):
            quote = copy.deepcopy(self.quote)
            for term in quote['conditions'].values():
                if mutation == 'missing': term.pop('validitySeries')
                if mutation == 'wrong-isin': term['validitySeries']['isin'] = 'OTHER'
                if mutation == 'wrong-source': term['validitySeries']['source'] = 'OTHER'
                if mutation == 'revoked': term['revoked'] = True
            if mutation == 'unverified': quote['productVerified'] = False
            with self.subTest(mutation=mutation):
                self.assertEqual(self.report(quote)[1]['assessment'], 'needs-attention')
        for now in (self.now-1, self.now+8*3600000):
            self.assertEqual(self.report(now=now)[1]['assessment'], 'needs-attention')

    def test_saved_acceptance_expires_without_a_new_audit(self):
        projected, _ = self.report()
        with patch('bob_diagnostics.time.time', return_value=self.now/1000+8*3600):
            self.assertEqual(diagnostics.summary({'products': projected})['assessment'], 'needs-attention')

    def test_missing_issuer_date_without_policy_is_still_a_warning(self):
        projected = diagnostics.product_snapshot({'items': [{'timeEvidence': {'terms': {
            'ko': {'validityUnconfirmed': True}, 'strike': {'validityUnconfirmed': True}}}}]})
        self.assertEqual(diagnostics.summary({'products': projected})['assessment'], 'needs-attention')


if __name__ == '__main__':
    unittest.main()
