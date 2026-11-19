import concurrent.futures
import subprocess
import threading
import time
import unittest
from unittest.mock import patch
import evaluator_runtime as r

class RuntimeTests(unittest.TestCase):
    def test_timeout_reports_ocr_blocker_without_payload(self):
        entered=threading.Event();release=threading.Event();logs=[]
        def ocr(*args,**kwargs):
            entered.set();release.wait(2);return 'ok'
        with patch.object(r,'MAX_QUEUE_SECONDS',.02),patch.object(r,'OCR_QUEUE_GRACE_SECONDS',.02),patch('builtins.print',side_effect=lambda line,**kw:logs.append(line)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                running=pool.submit(r.run,['python','private-path','--ocr'],runner=ocr)
                self.assertTrue(entered.wait(1))
                self.assertEqual(r.status()['activeKind'],'ocr')
                try:
                    with self.assertRaises(TimeoutError):r.run(['node','private-file'],input='private-data')
                    self.assertEqual(r.status()['activeKind'],'ocr')
                finally:release.set()
                self.assertEqual(running.result(),'ok')
        self.assertIsNone(r.status()['activeKind'])
        self.assertTrue(any('"blockedBy": "ocr"' in line for line in logs))
        self.assertNotIn('private',str(logs))

    def test_node_uses_one_bounded_grace_for_measured_ocr(self):
        entered=threading.Event();release=threading.Event();node_started=threading.Event()
        def ocr(*args,**kwargs):
            entered.set();release.wait(2);return 'ocr'
        def node(*args,**kwargs):node_started.set();return 'node'
        queue_timeouts_before=r.status()['queueTimeouts']
        with patch.object(r,'MAX_QUEUE_SECONDS',.02),patch.object(r,'OCR_QUEUE_GRACE_SECONDS',.2):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                image=pool.submit(r.run,['python','image','--ocr'],runner=ocr)
                self.assertTrue(entered.wait(1))
                analysis=pool.submit(r.run,['node','analysis'],runner=node)
                time.sleep(.05)
                self.assertFalse(analysis.done())
                release.set()
                self.assertEqual(image.result(),'ocr')
                self.assertEqual(analysis.result(),'node')
        self.assertTrue(node_started.is_set())
        self.assertEqual(r.status()['queueTimeouts'],queue_timeouts_before)

    def test_prior_ocr_still_gets_grace_after_signal_node_handoff(self):
        """OCR completed before the bound; a higher-priority Node takes over.

        The paper caller must retain one bounded OCR grace rather than
        misclassifying the new active Node as an ordinary long queue.
        """
        ocr_entered = threading.Event()
        ocr_release = threading.Event()
        signal_entered = threading.Event()
        signal_release = threading.Event()
        paper_started = threading.Event()
        def ocr(*args, **kwargs):
            ocr_entered.set()
            ocr_release.wait(2)
            return 'ocr'
        def signal(*args, **kwargs):
            signal_entered.set()
            signal_release.wait(2)
            return 'signal'
        def paper(*args, **kwargs):
            paper_started.set()
            return 'paper'
        before = r.status()['queueTimeouts']
        with patch.object(r,'MAX_QUEUE_SECONDS',.08), patch.object(r,'OCR_QUEUE_GRACE_SECONDS',.25):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                running_ocr = pool.submit(r.run,['python','image','--ocr'],runner=ocr,priority=2)
                self.assertTrue(ocr_entered.wait(1))
                waiting_paper = pool.submit(r.run,['node','paper-analysis'],runner=paper,priority=2)
                waiting_signal = pool.submit(r.run,['node','signal-analysis'],runner=signal,priority=1)
                deadline=time.monotonic()+1
                while r.status()['waiting'] < 2 and time.monotonic() < deadline:
                    time.sleep(.001)
                self.assertEqual(r.status()['waiting'],2)
                try:
                    ocr_release.set()
                    self.assertEqual(running_ocr.result(timeout=1),'ocr')
                    self.assertTrue(signal_entered.wait(1))
                    # Paper's ordinary 80ms deadline expires while the
                    # higher-priority Node is now active, NOT OCR.
                    time.sleep(.12)
                finally:
                    signal_release.set()
                    ocr_release.set()
                self.assertEqual(waiting_signal.result(timeout=1),'signal')
                self.assertEqual(waiting_paper.result(timeout=1),'paper')
        self.assertTrue(paper_started.is_set())
        self.assertEqual(r.status()['queueTimeouts'],before)

    def test_non_ocr_blocker_keeps_original_queue_bound(self):
        entered=threading.Event();release=threading.Event()
        def other(*args,**kwargs):entered.set();release.wait(2);return 'ok'
        with patch.object(r,'MAX_QUEUE_SECONDS',.02),patch.object(r,'OCR_QUEUE_GRACE_SECONDS',1):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                running=pool.submit(r.run,['python','worker'],runner=other)
                self.assertTrue(entered.wait(1))
                try:
                    started=time.monotonic()
                    with self.assertRaises(TimeoutError):
                        r.run(['node','analysis'],runner=lambda *a,**k:'node')
                    self.assertLess(time.monotonic()-started,.2)
                finally:release.set()
                self.assertEqual(running.result(),'ok')

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

    def test_guarded_ocr_runner_shares_capacity_and_releases_on_failure(self):
        entered=threading.Event();release=threading.Event();node_started=threading.Event()
        def ocr(*args,**kwargs):
            entered.set();release.wait(2);raise MemoryError('bounded child')
        def node(*args,**kwargs):node_started.set();return 'ok'
        with patch.object(r.subprocess,'run',side_effect=node):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                image=pool.submit(r.run,['python','ocr'],runner=ocr,priority=2)
                self.assertTrue(entered.wait(1))
                analysis=pool.submit(r.run,['node','analysis'])
                self.assertFalse(node_started.wait(.03))
                release.set()
                with self.assertRaises(MemoryError):image.result()
                self.assertEqual(analysis.result(),'ok')

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

