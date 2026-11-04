import unittest
from storage_pressure import policy, delay

class PressureTests(unittest.TestCase):
    def test_boundaries(self):
        for size, seconds in [(0,3600),(2499999999,3600),(2500000000,900),(3499999999,900),(3500000000,300),(5000000000,300)]:
            self.assertEqual(policy(size)['nextRunSeconds'],seconds)
    def test_unknown_and_failures_back_off(self):
        for size in (None,True,-1,'3500000000'):
            self.assertEqual(policy(size)['state'],'unknown')
        self.assertEqual(delay({'status':'deferred','pressure':policy(4500000000)}),3600)
        self.assertEqual(delay({'status':'archive-running'}),60)
        self.assertEqual(delay({'status':'checked','pressure':policy(4500000000)}),300)
