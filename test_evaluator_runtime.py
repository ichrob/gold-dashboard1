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
        with r._CONDITION: r._BUSY=True
        try:
            with patch.object(r,'MAX_QUEUE_SECONDS',.01),patch.object(r.subprocess,'run') as child:
                with self.assertRaises(TimeoutError):r.run(['node','worker.js'],timeout=1)
                child.assert_not_called()
        finally:
            with r._CONDITION: r._BUSY=False;r._CONDITION.notify_all()

    def test_priority_and_identical_inflight_requests(self):
        entered=threading.Event();release=threading.Event();order=[]
        def child(args, **kw):
            order.append(kw['input'])
            if kw['input']=='first': entered.set();release.wait(2)
            return {'input':kw['input']}
        with patch.object(r.subprocess,'run',side_effect=child):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                first=pool.submit(r.run,['node','w'],input='first')
                self.assertTrue(entered.wait(1))
                duplicate=pool.submit(r.run,['node','w'],input='first')
                paper=pool.submit(r.run,['node','w'],input='paper',priority=2)
                trade=pool.submit(r.run,['node','w'],input='trade',priority=0)
                deadline=time.monotonic()+1
                while r.status()['waiting']<2 and time.monotonic()<deadline:time.sleep(.001)
                release.set()
                a=first.result();b=duplicate.result();paper.result();trade.result()
                self.assertEqual(a,b);self.assertIsNot(a,b)
        self.assertEqual(order,['first','trade','paper'])
