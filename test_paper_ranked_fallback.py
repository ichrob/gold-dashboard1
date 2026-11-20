"""Regression: a verified SHORT below the displayed top three is not hidden.

Simulation-only; these tests never create a broker order or override KO guards.
"""
import unittest
from unittest.mock import patch

import paper_simulation as sim
import paper_evidence_chain


NOW = 1795197600000


def choice(isin, side='SHORT', **extra):
    return dict(isin=isin, direction=side, scope='XAU/USD',
                koGuardRequired=True, indicative=False, estimated=False,
                **extra)


def quote(isin, age=0, ask=20.0):
    return dict(isin=isin, found=True, marketOpen=True,
                bid=ask - 0.1, ask=ask, currency='EUR', source='test-issuer',
                bidAt=NOW-age, askAt=NOW-age, quoteAt=NOW-age)


class PaperRankedFallbackTests(unittest.TestCase):
    def setUp(self):
        self.first = [choice('SHORT1'), choice('SHORT2'), choice('SHORT3')]
        self.fourth = choice('SHORT4')
        self.selection = dict(
            choices=self.first,
            paperCandidates=self.first+[self.fourth],
            reasons=['First three issuer quotes not current'])

    def test_ranked_fallback_recovers_fourth_original_short(self):
        pool = sim.paper_entry_candidates(self.selection)
        self.assertEqual([c['isin'] for c in pool],
                         ['SHORT1', 'SHORT2', 'SHORT3', 'SHORT4'])
        prices = {c['isin']: quote(c['isin'], age=90001)
                  for c in self.first}
        prices['SHORT4'] = quote('SHORT4')
        with patch.object(sim.paper_ko_guard, 'entry_reason',
                          return_value=(None, {'valid': True})) as guard:
            candidate = sim.ranked_entry_candidate(
                pool, prices, {'direction': 'SHORT'}, NOW, 60.0,
                {'slippageBpsPerSide': 0, 'feeEurPerOrder': 0},
                require_ko=True)
        self.assertEqual(candidate['isin'], 'SHORT4')
        self.assertEqual(guard.call_count, 1)
        self.assertEqual(guard.call_args.args[0]['isin'], 'SHORT4')

    def test_fail_closed_if_fourth_quote_is_stale_or_budget_too_small(self):
        pool = sim.paper_entry_candidates(self.selection)
        prices = {c['isin']: quote(c['isin'], age=90001) for c in pool}
        with patch.object(sim.paper_ko_guard, 'entry_reason',
                          return_value=(None, {'valid': True})) as guard:
            candidate = sim.ranked_entry_candidate(
                pool, prices, {'direction': 'SHORT'}, NOW, 60.0,
                require_ko=True)
        self.assertEqual(candidate['isin'], 'SHORT1')
        guard.assert_not_called()
        prices['SHORT4'] = quote('SHORT4', ask=70)
        with patch.object(sim.paper_ko_guard, 'entry_reason',
                          return_value=(None, {'valid': True})):
            candidate = sim.ranked_entry_candidate(
                pool, prices, {'direction': 'SHORT'}, NOW, 60.0,
                require_ko=True)
        self.assertEqual(candidate['isin'], 'SHORT1')

    def test_indicative_or_wrong_direction_never_becomes_entry(self):
        selection = dict(
            choices=self.first,
            paperCandidates=self.first+[
                {**choice('ESTIMATE'), 'indicative': True},
                choice('WRONGSIDE', side='LONG'), self.fourth])
        pool = sim.paper_entry_candidates(selection)
        self.assertNotIn('ESTIMATE', [c['isin'] for c in pool])
        prices = {c['isin']: quote(c['isin'], age=90001) for c in pool}
        prices['WRONGSIDE'] = quote('WRONGSIDE')
        prices['SHORT4'] = quote('SHORT4')
        with patch.object(sim.paper_ko_guard, 'entry_reason',
                          side_effect=lambda c,*args: ('KO missing', None)
                          if c['isin']=='SHORT4' else (None, {'valid':True})):
            candidate = sim.ranked_entry_candidate(
                pool, prices, {'direction': 'SHORT'}, NOW, 60.0,
                require_ko=True)
        self.assertEqual(candidate['isin'], 'SHORT1')

    def test_legacy_selector_and_bounded_evidence(self):
        self.assertEqual(
            len(sim.paper_entry_candidates({'choices': self.first})), 3)
        extra = [choice('S'+str(i)) for i in range(25)]
        pool = sim.paper_entry_candidates(
            {'choices': self.first, 'paperCandidates': self.first+extra})
        self.assertEqual(len(pool), 12)
        evidence = paper_evidence_chain.capture_selection(
            self.selection, self.fourth, NOW)
        self.assertEqual(evidence['selectedIsin'], 'SHORT4')
        self.assertEqual([r['isin'] for r in evidence['rankedShortlist']],
                         ['SHORT1','SHORT2','SHORT3','SHORT4'])
        self.assertFalse(any('private' in r for r in evidence['rankedShortlist']))


if __name__ == '__main__':
    unittest.main()
