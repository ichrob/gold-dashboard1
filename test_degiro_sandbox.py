import unittest
from degiro_sandbox import PaperAdapter, run


class SandboxTests(unittest.TestCase):
    def buy(self):
        return dict(event='BUY_PAPER', quantity=2, price_eur=1.0, stop_eur=0.9)

    def test_replay_and_duplicate_protection(self):
        for scenario in ('target', 'stop_gap', 'trailing'):
            result = run(scenario)
            self.assertFalse(result['brokerConnected'])
            self.assertFalse(result['liveOrdersEnabled'])
            self.assertEqual(result['journal'][-1]['position'], 0)
            self.assertEqual(result['duplicateRetriesChecked'], len(result['journal']))
            self.assertTrue(all(not item['brokerSubmitted'] for item in result['journal']))
        self.assertEqual(run('stale')['journal'], [])

    def test_retry_after_sale_never_reopens(self):
        a = PaperAdapter()
        first = a.dispatch('buy', self.buy())
        a.dispatch('sell', dict(event='SELL_PAPER', quantity=2, price_eur=1.1))
        self.assertEqual(a.dispatch('buy', self.buy()), first)
        self.assertEqual(a.position, 0)
        self.assertEqual(len(a.journal), 2)

    def test_conflicting_key_and_stop_loosening(self):
        a = PaperAdapter()
        a.dispatch('buy', self.buy())
        with self.assertRaises(ValueError):
            a.dispatch('buy', {**self.buy(), 'quantity': 3})
        with self.assertRaises(ValueError):
            a.dispatch('stop', dict(event='TRAIL_PAPER', stop_eur=0.8))
        self.assertEqual(a.stop, 0.9)
        a.dispatch('stop', dict(event='TRAIL_PAPER', stop_eur=0.95))
        self.assertEqual(a.stop, 0.95)

    def test_invalid_events_do_not_mutate(self):
        a = PaperAdapter()
        for event in (dict(event='BUY'), {**self.buy(), 'price_eur': float('nan')},
                      {**self.buy(), 'quantity': True},
                      dict(event='SELL_PAPER', quantity=1, price_eur=1)):
            with self.assertRaises(ValueError):
                a.dispatch('bad', event)
        self.assertEqual(a.position, 0)
        self.assertEqual(a.journal, [])

    def test_receipts_cannot_mutate_internal_state(self):
        a = PaperAdapter()
        event = self.buy()
        receipt = a.dispatch('buy', event)
        receipt['event']['quantity'] = 999
        event['quantity'] = 1000
        self.assertEqual(a.dispatch('buy', self.buy())['event']['quantity'], 2)
        self.assertEqual(a.journal[0]['event']['quantity'], 2)

    def test_route_protected_and_panel_isolated(self):
        from pathlib import Path
        source = Path('server.py').read_text()
        protection = source.split('protected_api_path =', 1)[1].split('\n', 1)[0]
        self.assertIn('/api/degiro/sandbox', protection)
        import degiro_sandbox_panel
        self.assertIn("getElementById('bob-view-degiro')", degiro_sandbox_panel.PANEL)
        self.assertNotIn('localStorage', degiro_sandbox_panel.PANEL)


if __name__ == '__main__':
    unittest.main()
