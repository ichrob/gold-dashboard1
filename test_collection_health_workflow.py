from pathlib import Path
import unittest


class CollectionHealthWorkflowTests(unittest.TestCase):
    def test_registered_paper_inventory_is_checked_without_legacy_five_limit(self):
        workflow = Path('.github/workflows/bob-collection-health.yml').read_text(encoding='utf-8')
        self.assertNotIn("accountsTotal')==5", workflow)
        self.assertIn("accounts_total>=7", workflow)
        self.assertIn("accounts_checked==accounts_total", workflow)
        self.assertIn("all registered paper ledgers", workflow)

    def test_runtime_watchdog_does_not_gate_its_own_deployment(self):
        workflow = Path('.github/workflows/bob-collection-health.yml').read_text(encoding='utf-8')
        import yaml
        config = yaml.safe_load(workflow)
        triggers = config.get('on', config.get(True))
        self.assertNotIn('push', triggers)
        self.assertIn('schedule', triggers)
        self.assertIn('workflow_dispatch', triggers)
        self.assertNotIn('GITHUB_SHA', workflow)
        self.assertIn("monitor.get('status')=='ok'", workflow)
        self.assertIn("paper.get('realOrders') is False", workflow)


if __name__ == '__main__':
    unittest.main()
