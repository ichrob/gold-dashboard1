"""Vendor-safe cadence regression tests. No SnapTrade network requests."""
import copy
import unittest
from unittest.mock import patch
import snaptrade_bridge as bridge


class CadenceTests(unittest.TestCase):
    def setUp(self):
        keys=('_CONFIG','_LOADED','_NEXT','_LAST_ATTEMPT','_INTERACTIVE_UNTIL','_GENERATION')
        self.previous={key: getattr(bridge,key) for key in keys}
        self.previous_state=copy.deepcopy(bridge._STATE)
        bridge._CONFIG={'clientId':'test-client','consumerKey':'test-secret','personalFreeConfirmed':True}
        bridge._LOADED=True
        bridge._NEXT=0
        bridge._LAST_ATTEMPT=0
        bridge._INTERACTIVE_UNTIL=0
        bridge._STATE.clear()
        bridge._STATE.update(code='READY',snapshot=None)

    def tearDown(self):
        for key,value in self.previous.items():
            setattr(bridge,key,value)
        bridge._STATE.clear()
        bridge._STATE.update(self.previous_state)

    @staticmethod
    def snapshot():
        return {'accounts':[], 'completeConnections':True,
                'observedAt':'2026-10-21T10:00:00+00:00'}

    def test_background_refresh_is_six_hours_and_no_order(self):
        with patch.object(bridge.time,'monotonic',return_value=1000), \
             patch.object(bridge,'read_snapshot',return_value=self.snapshot()), \
             patch.object(bridge,'update_portfolio'):
            bridge.refresh()
            self.assertEqual(bridge._NEXT,1000+21600)
            self.assertEqual(bridge._LAST_ATTEMPT,1000)

    def test_authenticated_interactive_avoids_extra_fetch_in_first_ten_minutes(self):
        bridge._LAST_ATTEMPT=1000
        bridge._NEXT=1000+21600
        with patch.object(bridge.time,'monotonic',return_value=1100):
            bridge.mark_interactive()
            self.assertEqual(bridge._NEXT,1600)
            self.assertEqual(bridge._INTERACTIVE_UNTIL,1220)
            self.assertEqual(bridge.status()['intervalSeconds'],600)
        with patch.object(bridge.time,'monotonic',return_value=1600), \
             patch.object(bridge,'read_snapshot',return_value=self.snapshot()), \
             patch.object(bridge,'update_portfolio'):
            bridge.mark_interactive()
            bridge.refresh()
            self.assertEqual(bridge._NEXT,2200)
        with patch.object(bridge.time,'monotonic',return_value=3000):
            self.assertEqual(bridge.status()['intervalSeconds'],21600)

    def test_unauthenticated_core_status_never_marks_interactive(self):
        with patch.object(bridge.time,'monotonic',return_value=50):
            bridge.status()
            self.assertEqual(bridge._INTERACTIVE_UNTIL,0)


if __name__ == '__main__':
    unittest.main()
