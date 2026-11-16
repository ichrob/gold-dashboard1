"""Prospective, paper-only candidate selection regression checks.

No broker execution, no network fetching, no invented market/product prices.
"""
import copy
import unittest
from unittest.mock import patch

import paper_simulation as sim

NOW = 1791442800000
COST = {'feeEurPerOrder': 1.0, 'slippageBpsPerSide': 5}


def item(isin, direction='LONG', ko=True, **extra):
    return {'isin': isin, 'direction': direction, 'koGuardRequired': ko, **extra}


def quote(isin, ask=10.0, age=0):
    return {'isin': isin, 'found': True, 'marketOpen': True,
            'bid': ask - .1, 'ask': ask, 'currency': 'EUR',
            'source': 'dated issuer test', 'bidAt': NOW - age, 'askAt': NOW - age}


class RankedPaperCandidateTests(unittest.TestCase):
    def choose(self, ranked, prices, budget=100, direction='LONG', require_ko=True):
        return sim.ranked_entry_candidate(
            ranked, prices, {'direction': direction}, NOW,
            budget, COST, require_ko=require_ko)

    def test_skip_unaffordable_first_candidate_instead_of_stalling(self):
        ranked = [item('expensive'), item('affordable')]
        prices = {'expensive': quote('expensive', 650),
                  'affordable': quote('affordable', 17)}
        with patch.object(sim.paper_ko_guard, 'entry_reason', return_value=(None, {})):
            self.assertEqual(self.choose(ranked, prices, budget=520)['isin'], 'affordable')

    def test_preserves_original_rank_for_equally_eligible_candidates(self):
        ranked = [item('first'), item('second')]
        prices = {key: quote(key) for key in ('first', 'second')}
        original = copy.deepcopy((ranked, prices))
        with patch.object(sim.paper_ko_guard, 'entry_reason', return_value=(None, {})):
            self.assertEqual(self.choose(ranked, prices)['isin'], 'first')
        self.assertEqual((ranked, prices), original)

    def test_stale_unknown_and_indicative_never_beat_fresh_eligible(self):
        ranked = [item('stale'), item('missing'), item('indicative', indicative=True),
                  item('fresh')]
        prices = {'stale': quote('stale', age=90001),
                  'indicative': quote('indicative'),
                  'fresh': quote('fresh')}
        with patch.object(sim.paper_ko_guard, 'entry_reason', return_value=(None, {})):
            self.assertEqual(self.choose(ranked, prices)['isin'], 'fresh')

    def test_both_product_direction_fields_must_agree_with_signal(self):
        ranked = [item('opposite', direction='SHORT'),
                  item('contradictory', productDirection='SHORT'),
                  item('matching')]
        prices = {x['isin']: quote(x['isin']) for x in ranked}
        with patch.object(sim.paper_ko_guard, 'entry_reason', return_value=(None, {})):
            self.assertEqual(self.choose(ranked, prices)['isin'], 'matching')
            self.assertIsNone(self.choose(ranked[:2], prices))

    def test_ko_proof_required_and_failed_guard_cannot_be_skipped(self):
        ranked = [item('unproved', ko=False), item('blocked'), item('valid')]
        prices = {x['isin']: quote(x['isin']) for x in ranked}
        def guard(choice, *_):
            return ('KO proof invalid', {}) if choice['isin'] == 'blocked' else (None, {})
        with patch.object(sim.paper_ko_guard, 'entry_reason', side_effect=guard):
            self.assertEqual(self.choose(ranked, prices)['isin'], 'valid')
        with patch.object(sim.paper_ko_guard, 'entry_reason', side_effect=RuntimeError('no proof')):
            self.assertEqual(self.choose(ranked[:2], prices)['isin'], 'unproved')

    def test_includes_existing_fee_and_slippage_reserve(self):
        ranked = [item('too-expensive'), item('within-budget')]
        prices = {'too-expensive': quote('too-expensive', 19.6),
                  'within-budget': quote('within-budget', 12)}
        with patch.object(sim.paper_ko_guard, 'entry_reason', return_value=(None, {})):
            self.assertEqual(self.choose(ranked, prices, budget=21)['isin'], 'within-budget')

    def test_no_safe_candidate_keeps_diagnostic_blocker_without_fake_fill(self):
        ranked = [item('stale'), item('missing')]
        prices = {'stale': quote('stale', age=200000)}
        with patch.object(sim.paper_ko_guard, 'entry_reason', return_value=(None, {})):
            self.assertEqual(self.choose(ranked, prices)['isin'], 'stale')
        self.assertIsNone(self.choose([], prices))
        self.assertIsNone(self.choose([item('short', direction='SHORT')], prices))


if __name__ == '__main__':
    unittest.main()
