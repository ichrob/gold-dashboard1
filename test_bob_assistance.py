import unittest
from unittest.mock import patch
import bob_assistance as a

class AssistanceTest(unittest.TestCase):
    def setUp(self):
        a._pending.clear()
    def test_only_anonymous_codes(self):
        with patch.object(a.bob_repair_store, 'queue_event') as queue:
            for payload in ({'code':'private-isin'}, {'code':'trade-setup-stalled','purchase':'private'}, [], {'code':[]}):
                with self.assertRaises((ValueError, TypeError)):
                    a.report(payload)
            queue.assert_not_called()
    def test_deduplicated_escalation(self):
        with patch.object(a.bob_repair_store, 'queue_event') as queue:
            for _ in range(3):
                self.assertEqual(a.report({'code':'trade-setup-stalled'})['status'],'queued')
            queue.assert_called_once_with('detected','trade-setup-stalled')
            self.assertEqual(a.pending_codes(),['trade-setup-stalled'])
if __name__=='__main__': unittest.main()
