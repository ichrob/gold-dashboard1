import unittest
from unittest.mock import Mock, patch
import paper_simulation as sim

class WakeupTest(unittest.TestCase):
    def test_new_bundle_wakes_existing_worker_and_keeps_latest(self):
        event=__import__('threading').Event()
        worker=Mock();worker.is_alive.return_value=True
        with patch.object(sim,'_bundle_ready',event), patch.object(sim,'_thread',worker), patch.object(sim,'_latest',None):
            first={'spots':{'xaus':1}}
            newest={'spots':{'xaus':2}}
            sim.enqueue(first,Mock())
            self.assertTrue(event.wait(timeout=.01))
            event.clear()
            sim.enqueue(newest,Mock())
            self.assertTrue(event.wait(timeout=.01))
            self.assertIs(sim._latest,newest)
            worker.start.assert_not_called()

if __name__=='__main__':unittest.main()
