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
        self.assertEqual(result['counts']['partial'], 94)
        self.assertEqual(result['counts']['planned'], 0)
        self.assertEqual(result['moduleInventory']['status'], 'structural-only')
        self.assertEqual(result['moduleInventory']['goalCount'], 100)
        self.assertEqual(result['moduleInventory']['moduleCount'], 19)
        self.assertEqual(result['moduleInventory']['individuallyVerified'], 0)
        self.assertEqual({r['id']: r['codeEvidence'] for r in m['tasks']
                          if r['id'] in (8, 19)}, {
            8: 'diagnostic_history.py',
            19: 'diagnostic_state_compare.py',
        })
        self.assertEqual(sum(result['counts'].values()), 100)
        self.assertEqual(result['counts']['requires-device'], 5)

    def test_every_declared_code_module_exists_without_claiming_completion(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        paths = [ROOT / row['codeEvidence'] for row in m['tasks']]
        self.assertTrue(all(path.is_file() for path in paths),
                        [str(path.relative_to(ROOT)) for path in paths if not path.is_file()])
        trades = {row['id']: row['codeEvidence'] for row in m['tasks']
                  if 61 <= row['id'] <= 70}
        self.assertEqual(trades, {
            61: 'real_trade_journal.py',
            62: 'trade_risk_review.py',
            63: 'product_trade_curve.js',
            64: 'stop_target_audit.py',
            65: 'bob_stop_assistant.js',
            66: 'ko_protection.py',
            67: 'bob_stop_assistant.js',
            68: 'trade_risk_review.py',
            69: 'push_delivery_history.py',
            70: 'trade_learning_review.py',
        })
        self.assertEqual(diag.read_access_coverage(m)['verified'], 0)
        self.assertTrue(all(row['verified'] is False for row in m['tasks']))

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
