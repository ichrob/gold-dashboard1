from pathlib import Path
import unittest


class CollectionHealthWorkflowTests(unittest.TestCase):
    def test_registered_paper_inventory_is_checked_without_legacy_five_limit(self):
        workflow = Path('.github/workflows/bob-collection-health.yml').read_text(encoding='utf-8')
        self.assertNotIn("accountsTotal')==5", workflow)
        self.assertIn("accounts_total>=7", workflow)
        self.assertIn("accounts_checked==accounts_total", workflow)
        self.assertIn("all registered paper ledgers", workflow)


if __name__ == '__main__':
    unittest.main()
