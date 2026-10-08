import concurrent.futures
import subprocess
import threading
import time
import unittest
from unittest.mock import patch
import evaluator_runtime as r

class RuntimeTests(unittest.TestCase):
    def test_concurrent_analysis_and_product_work_are_serialized(self):
        active=0
        peak=0
        guard=threading.Lock()
        def child(args, **kw):
            nonlocal active,peak
            with guard:
                active+=1;peak=max(peak,active)
            time.sleep(.02)
            with guard: active-=1
            self.assertEqual(args[:2],['node','--v8-pool-size=1'])
            return kw['input']
        with patch.object(r.subprocess,'run',side_effect=child):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda i:r.run(['node','worker.js'],input=str(i),timeout=6),range(4)))
        self.assertEqual(peak,1)
        self.assertEqual(results,['0','1','2','3'])

    def test_timeout_releases_capacity(self):
        with patch.object(r.subprocess,'run',side_effect=subprocess.TimeoutExpired('node',1)):
            with self.assertRaises(subprocess.TimeoutExpired):r.run(['node','worker.js'],timeout=1)
        with patch.object(r.subprocess,'run',return_value='recovered'):
            self.assertEqual(r.run(['node','worker.js'],timeout=1),'recovered')

    def test_full_queue_is_bounded_and_does_not_start_child(self):
        r._SLOT.acquire()
        try:
            with patch.object(r,'MAX_QUEUE_SECONDS',.01),patch.object(r.subprocess,'run') as child:
                with self.assertRaises(TimeoutError):r.run(['node','worker.js'],timeout=1)
                child.assert_not_called()
        finally:r._SLOT.release()
