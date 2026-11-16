import copy
import json
import unittest
import bob_diagnostics as d


class ComparisonBudgetTests(unittest.TestCase):
    def source(self):
        return {'areas': {'comparisonEvidence': {
            'status': 'partial', 'observedAt': '2026-11-15T14:00:00+00:00',
            'readOnly': True, 'realOrders': False, 'scope': 'bounded-sample-only',
            'comparisonHealth': {'status': 'partial', 'items': {
                'signals': {'status': 'unavailable'}}},
            'gapEvidence': {'paperInputArchive': {
                'status': 'partial', 'counts': {'queryUnavailable': 2},
                'sampledDistinctClocks': 3, 'totalDistinctClocks': 8,
                'items': [{'payload': 'x' * 20000}], 'scope': 'no-backfill'},
                'paperInputLatest': {'status': 'not-yet-observed', 'observedAt': None,
                    'profiles': [{'payload': 'y' * 12000}], 'profilesObserved': 0}},
            'accountSamples': [{'profile': 'paper',
                'forwardValidationStatus': 'not-started', 'forwardValidation': None,
                'recentCases': {'status': 'observed', 'scope': 'latest-five',
                    'items': [{'status': 'inconclusive', 'startedAt': 123,
                        'netReturnKnown': False, 'performanceEligible': False,
                        'evidenceChain': {'complete': False, 'brokerExecutionVerified': False},
                        'events': [{'details': 'z' * 18000}]}]}}]}}}

    def test_archive_detail_does_not_erase_counts_failures_and_case_evidence(self):
        source = self.source()
        original = copy.deepcopy(source)
        result = d.bounded_report(source, 4000)
        view = result['areas']['comparisonEvidence']
        self.assertNotIn('comparisonEvidence', result['omittedAreas'])
        for key in ('status', 'observedAt', 'scope', 'readOnly', 'realOrders', 'comparisonHealth'):
            self.assertEqual(view[key], original['areas']['comparisonEvidence'][key])
        archive = view['gapEvidence']['paperInputArchive']
        self.assertEqual(archive['counts']['queryUnavailable'], 2)
        self.assertEqual(archive['sampledDistinctClocks'], 3)
        self.assertEqual(archive['totalDistinctClocks'], 8)
        self.assertEqual(archive['scope'], 'no-backfill')
        self.assertEqual(archive['omittedSections'], ['items'])
        latest = view['gapEvidence']['paperInputLatest']
        self.assertEqual(latest['status'], 'not-yet-observed')
        self.assertIsNone(latest['observedAt'])
        case = view['accountSamples'][0]['recentCases']['items'][0]
        self.assertEqual(case['startedAt'], 123)
        self.assertFalse(case['netReturnKnown'])
        self.assertFalse(case['performanceEligible'])
        self.assertFalse(case['evidenceChain']['brokerExecutionVerified'])
        self.assertEqual(case['omittedSections'], ['events'])
        self.assertEqual(source, original)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False,
            separators=(',', ':')).encode()), 4000)

    def test_duplicate_entry_history_is_referenced_not_repeated(self):
        source = self.source()
        blocks = {'status': 'partial', 'observedAt': 123,
                  'accounts': [{'reason': 'missing-price', 'history': 'x' * 6000}]}
        source['areas']['entryBlockEvidence'] = blocks
        source['areas']['comparisonEvidence']['entryBlockEvidence'] = copy.deepcopy(blocks)
        source['areas']['comparisonHealth'] = copy.deepcopy(
            source['areas']['comparisonEvidence']['comparisonHealth'])
        original = copy.deepcopy(source)
        result = d.bounded_report(source, 10000)
        view = result['areas']['comparisonEvidence']
        self.assertNotIn('comparisonEvidence', result['omittedAreas'])
        self.assertEqual(result['areas']['entryBlockEvidence'], blocks)
        self.assertEqual(view['entryBlockEvidence']['sourceArea'], 'entryBlockEvidence')
        self.assertEqual(view['entryBlockEvidence']['sourceStatus'], 'partial')
        self.assertEqual(view['comparisonHealth']['status'], 'omitted-duplicate')
        self.assertEqual(source, original)
        self.assertLessEqual(len(json.dumps(result, ensure_ascii=False,
            separators=(',', ':')).encode()), 10000)

    def test_distinct_observations_are_never_replaced_by_references(self):
        source = self.source()
        source['areas']['comparisonHealth'] = {'status': 'observed', 'observedAt': 456}
        result = d.bounded_report(source, 4000)
        self.assertEqual(result['areas']['comparisonEvidence']['comparisonHealth']['status'],
                         'partial')

    def test_fitting_payload_remains_complete(self):
        source = self.source()
        self.assertEqual(d.bounded_report(source, 100000), source)

    def test_remaining_oversize_still_has_explicit_area_omission(self):
        source = self.source()
        source['areas']['comparisonEvidence']['uncompactable'] = 'x' * 10000
        result = d.bounded_report(source, 4000)
        self.assertIn('comparisonEvidence', result['omittedAreas'])

    def test_missing_or_unavailable_source_is_not_promoted(self):
        for source in (None, {}, {'status': 'unavailable', 'reason': 'query-failed'}):
            self.assertEqual(d.compact_comparison_evidence(source), source)


if __name__ == '__main__':
    unittest.main()
