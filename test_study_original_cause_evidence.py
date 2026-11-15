"""Prospective source-clock and inconclusive-exit evidence for Bob quality study.

These tests do NOT weaken live candle freshness or reconstruct past trades.
"""
import copy
import unittest

import bob_diagnostics
import research_restart as r
from test_research_restart import NOW, sample


class OriginalEvidenceTests(unittest.TestCase):
    def test_identity_and_stale_source_cannot_be_admitted(self):
        b, m = sample()
        b['spots']['is_genuine_xauusd_spot'] = False
        state, closed = r.advance(r.seed(NOW), b, m, NOW)
        self.assertEqual(closed, [])
        self.assertEqual(state['quality']['invalid'], 1)
        witness = state['quality']['recentOriginalFailureEvidence'][-1]
        self.assertEqual(witness['reasonCode'], 'spot-identity-unverified')
        self.assertEqual(witness['clockRelation'], 'within-60s')
        self.assertFalse(witness['identityVerified'])
        self.assertEqual(witness['timeframe'], '15m')
        self.assertTrue(all(not c['open'] for c in state['studies'].values()))

        old_b, old_m = sample()
        state, _ = r.advance(state, old_b, old_m, NOW + 61000)
        witness = state['quality']['recentOriginalFailureEvidence'][-1]
        self.assertEqual(witness['reasonCode'], 'spot-source-not-fresh')
        self.assertEqual(witness['clockRelation'], 'stale-over-60s')
        self.assertEqual(witness['sourceAgeMs'], 61000)
        self.assertEqual(state['quality']['invalid'], 2)
        self.assertLessEqual(len(state['quality']['recentOriginalFailureEvidence']), 16)

    def test_failure_witness_expires_after_valid_followups_and_at_read_time(self):
        bundle, market = sample()
        bundle['spots']['is_genuine_xauusd_spot'] = False
        state, _ = r.advance(r.seed(NOW), bundle, market, NOW)
        self.assertEqual(len(state['quality']['recentOriginalFailureEvidence']), 1)

        # The inclusive twenty-minute boundary remains recent.
        at_boundary = NOW + 20 * 60000
        state, _ = r.advance(state, *sample(at_boundary), at_boundary)
        self.assertEqual(len(state['quality']['recentOriginalFailureEvidence']), 1)

        # A valid next cycle must prune the expired witness without waiting for
        # another failure. Cumulative counts are preserved.
        after_boundary = at_boundary + 1
        state, _ = r.advance(state, *sample(after_boundary), after_boundary)
        self.assertEqual(state['quality']['recentOriginalFailureEvidence'], [])
        self.assertEqual(state['quality']['invalid'], 1)
        self.assertEqual(state['quality']['originalBlockReasons'],
                         {'spot-identity-unverified': 1})

        # Read-time filtering is independent of worker maintenance: an old
        # stored snapshot cannot claim an expired witness is still recent.
        stale_state = r.seed(NOW)
        stale_state['quality']['recentOriginalFailureEvidence'] = [
            r.original_failure_evidence(
                {'sourceAt': NOW, 'analysisBarAt': NOW,
                 'reasonCode': 'spot-source-not-fresh',
                 'closedSignalBarMatched': True},
                sample()[0], sample()[1], NOW, '15m')]
        report = {'qualityCampaign': {
            'status': 'collecting', 'checkedAt': NOW,
            'studies': r.study_rows(stale_state)}}
        brief = bob_diagnostics.new_studies_brief(report, after_boundary)
        reaction = next(x for x in brief['quality']['studies']
                        if x['id'] == 'reaction')
        self.assertEqual(reaction.get('recentOriginalFailureEvidence', []), [])

    def test_future_quote_is_rejected_even_if_market_price_matches(self):
        bundle, market = sample(NOW + 1000)
        result, _ = r.advance(r.seed(NOW), bundle, market, NOW)
        evidence = result['quality']['recentOriginalFailureEvidence'][-1]
        self.assertEqual(evidence['clockRelation'], 'future')
        self.assertEqual(evidence['sourceAgeMs'], -1000)
        self.assertEqual(evidence['reasonCode'], 'spot-source-not-fresh')
        self.assertEqual(result['quality']['original'], 0)
        self.assertTrue(all(x['started'] == 0 for x in result['studies'].values()))

    def test_virtual_replay_clock_must_be_explicit_not_live_bypassed(self):
        # A 120s WALL pause cannot make an old source quote admissible.
        bundle, market = sample()
        wall, _ = r.advance(r.seed(NOW), bundle, market, NOW + 120000)
        self.assertEqual(wall['quality']['invalid'], 1)
        self.assertEqual(
            wall['quality']['recentOriginalFailureEvidence'][-1]['clockRelation'],
            'stale-over-60s')
        self.assertEqual(sum(c['started'] for c in wall['studies'].values()), 0)
        # A genuine separate replay runs its own explicit event clock. This
        # does not amend wall-clock live admissions or backfill unknown quotes.
        replay, _ = r.advance(r.seed(NOW), *sample(), NOW)
        self.assertEqual(replay['quality']['original'], 1)
        self.assertEqual(replay['quality']['invalid'], 0)

    def test_historical_invalid_total_never_gets_invented_causes(self):
        state = r.seed(NOW)
        state['quality']['invalid'] = 713
        state['quality']['originalBlockReasons'] = {
            'spot-source-not-fresh': 244, 'spot-identity-unverified': 127}
        state['studies']['entry-delay']['inconclusive'] = 35
        cases = {x['id']: x for x in r.study_rows(state)}
        self.assertEqual(cases['reaction']['originalLegacyUnclassified'], 342)
        self.assertEqual(cases['reaction']['recentOriginalFailureEvidence'], [])
        self.assertEqual(cases['entry-delay']['historicalInconclusiveUnclassified'], 35)
        self.assertEqual(cases['entry-delay']['inconclusiveEvidenceReasons'], {})


class TerminalEvidenceTests(unittest.TestCase):
    def test_real_original_gap_over_ninety_seconds_remains_inconclusive(self):
        bundle, market = sample()
        state, _ = r.advance(r.seed(NOW), bundle, market, NOW)
        bundle, market = sample(NOW + r.HORIZON)
        state, closed = r.advance(state, bundle, market, NOW + r.HORIZON)
        self.assertEqual(len(closed), 3)
        for case in closed:
            self.assertEqual(case['status'], 'inconclusive')
            self.assertEqual(case['returnsPct'], {})
            self.assertEqual(case['outcomeEvidenceCode'], 'original-source-gap-over-90s')
        for study in r.STUDIES:
            self.assertEqual(
                state['studies'][study]['inconclusiveEvidenceReasons'],
                {'original-source-gap-over-90s': 1})

    def test_unobserved_terminal_quote_is_not_fabricated(self):
        state, _ = r.advance(r.seed(NOW), *sample(), NOW)
        closed = []
        # Continuous original ticks before terminal due, no gap larger than 90s.
        for elapsed in range(30000, r.HORIZON, 30000):
            state, out = r.advance(state, *sample(NOW + elapsed), NOW + elapsed)
            closed += out
        self.assertEqual(closed, [])
        # A genuine quote immediately before the horizon avoids conflating a
        # terminal-window omission with a separate >90s source-path gap.
        last_before_due = r.HORIZON - 1
        state, out = r.advance(state, *sample(NOW + last_before_due),
                               NOW + last_before_due)
        self.assertEqual(out, [])
        # At/after terminal, spot identity stays unverified. Even though wall
        # time advances normally, no quote may be admitted as a virtual exit.
        for elapsed in (r.HORIZON, r.HORIZON + 30000,
                        r.HORIZON + 60000, r.HORIZON + 61000):
            b, m = sample(NOW + elapsed)
            b['spots']['is_genuine_xauusd_spot'] = False
            state, out = r.advance(state, b, m, NOW + elapsed)
            closed.extend(out)
        self.assertEqual(len(closed), 3)
        self.assertTrue(all(x['status'] == 'inconclusive' for x in closed))
        self.assertTrue(all(x['exit'] is None for x in closed if 'exit' in x))
        self.assertTrue(all(x['outcomeEvidenceCode'] ==
                            'terminal-original-exit-unobserved' for x in closed))
        self.assertTrue(all(x['returnsPct'] == {} for x in closed))

    def test_unobserved_delayed_entry_classified_without_fake_fill(self):
        state, _ = r.advance(r.seed(NOW), *sample(), NOW)
        state, _ = r.advance(state, *sample(NOW + 50000), NOW + 50000)
        # Source-to-source 80s, worker-to-worker 80s, both under the 90s
        # missing-path threshold. But the 60s delayed leg's grace has passed.
        state, _ = r.advance(state, *sample(NOW + 130000), NOW + 130000)
        c = state['studies']['entry-delay']['open'][0]
        self.assertTrue(c['evidenceFlags']['delayedEntryWindowMissed'])
        self.assertIsNone(c['legs']['60s']['entry'])
        closed = []
        for elapsed in list(range(160000, r.HORIZON, 30000)) + [r.HORIZON]:
            state, out = r.advance(state, *sample(NOW + elapsed), NOW + elapsed)
            closed.extend(out)
        delay = next(x for x in closed if x['study'] == 'entry-delay')
        self.assertEqual(delay['status'], 'inconclusive')
        self.assertEqual(delay['outcomeEvidenceCode'],
                         'delayed-entry-original-unobserved')
        self.assertEqual(delay['returnsPct'], {})
        self.assertEqual(
            state['studies']['entry-delay']['inconclusiveEvidenceReasons'],
            {'delayed-entry-original-unobserved': 1})


class PrivateBriefTests(unittest.TestCase):
    def test_bounded_private_projection_excludes_raw_price_and_secret(self):
        b, m = sample()
        b['spots']['is_genuine_xauusd_spot'] = False
        state, _ = r.advance(r.seed(NOW), b, m, NOW)
        report = {'qualityCampaign': {
            'status': 'collecting', 'checkedAt': NOW,
            'studies': r.study_rows(state)},
            'shadowStudies': {'status': 'observed',
                              'entryExitComparison': {'status': 'observed'}},
            'intradayTimingStudy': {'status': 'observed'},
            'rapidLeverageStudy': {'status': 'observed'}}
        brief = bob_diagnostics.new_studies_brief(report, NOW)
        rows = {x['id']: x for x in brief['quality']['studies']}
        self.assertEqual(rows['reaction']['recentOriginalFailureEvidence'][0]['reasonCode'],
                         'spot-identity-unverified')
        self.assertEqual(rows['reaction']['originalLegacyUnclassified'], 0)
        encoded = __import__('json').dumps(rows)
        for forbidden in ('sourcePrice', 'api_key', 'password', '"price":',
                          'accessToken', 'accountNumber'):
            self.assertNotIn(forbidden, encoded)


if __name__ == '__main__':
    unittest.main()
