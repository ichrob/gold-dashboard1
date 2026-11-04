import json
import unittest
import feature_storage as f
import storage_brief


class FeatureStorageTests(unittest.TestCase):
    def test_complete_small_tables_not_limited_to_top_twelve(self):
        relations = {t: 8192 for tables in f.GROUPS.values() for t in tables}
        relations['private_token_table'] = 123
        result = f.report([(100, 999, relations)], 120)
        self.assertEqual(result['groups']['videoAnalysis']['allocatedBytes'], 40960)
        self.assertEqual(result['status'], 'observed')
        self.assertNotIn('private_token_table', json.dumps(result))
        self.assertIsNone(result['voice']['allocatedBytes'])
        brief = storage_brief.project({'featureAllocation': result, 'observedAt': 120})
        self.assertEqual(brief['featureAllocation'], result)
        self.assertIsNone(result['physicalBytesFreed'])

    def test_missing_not_zero_and_stale_not_fresh(self):
        result = f.report([(100, 999, {'bob_research_replays': 0})], 4000)
        self.assertIsNone(result['groups']['videoAnalysis']['allocatedBytes'])
        self.assertEqual(result['groups']['strategyReplay']['status'], 'stale')
        self.assertEqual(result['groups']['strategyReplay']['allocatedBytes'], 0)
        self.assertEqual(f.report([], 1)['status'], 'not-observed')

    def test_malformed_values_and_untrusted_fields(self):
        for bad in (True, -1, float('inf'), 'secret', 10**14):
            result = f.project({'sampleAt': 100, 'relations': {
                'bob_research_replays': bad}, 'secret': 'TOKEN'}, 99)
            self.assertEqual(result['status'], 'invalid-timestamp')
            self.assertIsNone(result['groups']['strategyReplay']['allocatedBytes'])
            self.assertNotIn('TOKEN', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
