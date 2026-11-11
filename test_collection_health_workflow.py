from pathlib import Path
import unittest


class CollectionHealthWorkflowTests(unittest.TestCase):
    def test_registered_paper_inventory_is_checked_without_legacy_five_limit(self):
        workflow = Path('.github/workflows/bob-collection-health.yml').read_text(encoding='utf-8')
        self.assertNotIn("accountsTotal')==5", workflow)
        self.assertIn("accounts_total>=7", workflow)
        self.assertIn("accounts_checked==accounts_total", workflow)
        self.assertIn("all registered paper ledgers", workflow)

    def test_push_rollout_gets_one_bounded_revision_and_profile_warmup_retry(self):
        workflow = Path('.github/workflows/bob-collection-health.yml').read_text(encoding='utf-8')
        self.assertEqual(workflow.count('sleep 20'), 1)
        self.assertIn('push.get(\'build\') != expected', workflow)
        self.assertIn('scanner.get(\'build\') != expected', workflow)
        self.assertIn("paperObservation') or {}).get('state') == 'degraded'", workflow)
        self.assertIn("assert push.get('build')==expected", workflow)
        self.assertIn("assert health.get('build')==expected", workflow)
        self.assertNotIn('while true', workflow)
        self.assertNotIn('until true', workflow)


if __name__ == '__main__':
    unittest.main()
