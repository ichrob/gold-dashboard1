"""Forward-only evidence for a qualifying PAPER candidate below visible Top 3.

Synthetic data only: no broker execution, original quote rewriting or cash mutation.
"""
import unittest

import paper_evidence_chain
import paper_simulation


NOW = 1795197600000


def candidate(isin, **extra):
    return dict(isin=isin, direction='SHORT', scope='XAU/USD',
                koGuardRequired=True, indicative=False, estimated=False,
                score=50, source='dated-source', at=NOW, **extra)


class PaperFallbackEvidenceTests(unittest.TestCase):
    def test_fourth_qualified_entry_keeps_original_selection_proof(self):
        visible = [candidate('A'), candidate('B'), candidate('C')]
        fourth = candidate('D')
        selection = {'choices': visible,
                     'researchCandidates': visible+[fourth]}
        actual = paper_simulation.paper_entry_candidates(selection)
        self.assertEqual([c['isin'] for c in actual], ['A','B','C','D'])
        evidence = paper_evidence_chain.capture_selection(
            {'choices': actual}, fourth, NOW)
        self.assertEqual(evidence['capturedAt'], NOW)
        self.assertEqual(evidence['selectedIsin'], 'D')
        self.assertIn('D', [x['isin'] for x in evidence['rankedShortlist']])
        self.assertEqual([x['isin'] for x in selection['choices']],
                         ['A','B','C'])
        # A fallback entry must pass the downstream selection-evidence stage
        # even when product exit evidence is not yet known.
        case = {'startedAt': NOW, 'product': {'isin': 'D'},
                'selectionEvidence': evidence}
        review = paper_evidence_chain.review(case)
        selection_stage = next(s for s in review['stages']
                               if s['label'] == 'Gespeicherte Ranglisten-Auswahl')
        self.assertTrue(selection_stage['observed'])

    def test_no_unguarded_raw_quote_or_unbounded_input_is_captured(self):
        entries = [candidate(str(i)) for i in range(25)]
        for entry in entries:
            entry['privatePayload'] = 'must not persist'
        evidence = paper_evidence_chain.capture_selection(
            {'choices': entries}, entries[14], NOW)
        self.assertEqual(len(evidence['rankedShortlist']), 15)
        self.assertEqual(evidence['rankedShortlist'][-1]['isin'], '14')
        self.assertTrue(all('privatePayload' not in p
                            for p in evidence['rankedShortlist']))

    def test_legacy_top_three_snapshot_unchanged(self):
        entries = [candidate('A'), candidate('B'), candidate('C')]
        evidence = paper_evidence_chain.capture_selection(
            {'choices': entries}, entries[0], NOW)
        self.assertEqual([x['isin'] for x in evidence['rankedShortlist']],
                         ['A','B','C'])


if __name__ == '__main__':
    unittest.main()
