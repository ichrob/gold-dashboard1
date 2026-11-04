import unittest
from storage_pressure import policy, delay

class PressureTests(unittest.TestCase):
    def test_boundaries(self):
        for size, seconds in [(0,3600),(499999999,3600),(500000000,900),(699999999,900),(700000000,300),(5000000000,300)]:
            self.assertEqual(policy(size)['nextRunSeconds'],seconds)
    def test_unknown_and_failures_back_off(self):
        for size in (None,True,-1,'700000000'):
            self.assertEqual(policy(size)['state'],'unknown')
        self.assertEqual(delay({'status':'deferred','pressure':policy(4500000000)}),3600)
        self.assertEqual(delay({'status':'archive-running'}),60)
        self.assertEqual(delay({'status':'checked','pressure':policy(4500000000)}),300)

    def test_upgraded_volume_does_not_slow_existing_offload(self):
        from storage_capacity import ALLOCATION_BYTES, MAX_VOLUME_BYTES
        self.assertEqual(ALLOCATION_BYTES, 5_000_000_000)
        self.assertGreater(MAX_VOLUME_BYTES, 700_000_000)
        self.assertEqual(policy(652_850_879)['nextRunSeconds'], 900)
        self.assertEqual(policy(763_000_000)['nextRunSeconds'], 300)
        # A failed cycle must back off even above the operating target.
        self.assertEqual(delay({'status': 'failed', 'pressure': policy(763_000_000)}), 3600)
