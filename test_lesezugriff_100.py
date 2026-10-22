"""Guard the 100-point Bob diagnostic inventory against misleading completion."""
import json
import unittest
from pathlib import Path
import bob_diagnostics as diag

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'Besser_werden' / 'lesezugriff_100_status.json'

class ReadAccessCoverageTests(unittest.TestCase):
    def test_all_100_require_evidence_and_are_not_marked_done(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        result = diag.read_access_coverage(m)
        self.assertEqual(result['total'], 100)
        self.assertEqual(result['verified'], 0)
        self.assertEqual(result['unverified'], 100)
        self.assertEqual(result['status'], 'inventory-only')
        self.assertEqual(sum(result['counts'].values()), 100)
        self.assertEqual(result['counts']['requires-device'], 5)

    def test_reject_inconsistent_or_fabricated_completion(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        m['tasks'][0]['verified'] = True
        self.assertEqual(diag.read_access_coverage(m)['status'], 'unavailable')
        m['tasks'][0]['verified'] = False
        m['tasks'][1]['id'] = 1
        self.assertEqual(diag.read_access_coverage(m)['status'], 'unavailable')
        self.assertEqual(diag.read_access_coverage(None)['status'], 'unavailable')

if __name__ == '__main__':
    unittest.main()
