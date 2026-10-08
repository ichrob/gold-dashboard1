import threading
import unittest
from concurrent.futures import Future
from unittest.mock import patch
import quote_runtime as q

class QuoteRuntimeTests(unittest.TestCase):
    def setUp(self):
        patcher=patch.object(q,'_READY',q.OrderedDict())
        patcher.start();self.addCleanup(patcher.stop)

    def test_slow_product_does_not_block_other_product(self):
        release=threading.Event()
        def fetch(isin):
            if isin=='slow': release.wait(2)
            return {'isin':isin}
        try:
            with patch.object(q,'WAIT_SECONDS',.01):
                self.assertEqual(q.run('slow',fetch)['quoteFailureCode'],'PRODUCT_TIMEOUT')
                first=q._PENDING['slow']
                self.assertEqual(q.run('fast',fetch),{'isin':'fast'})
                q.run('slow',fetch)
                self.assertIs(q._PENDING['slow'],first)
        finally:release.set();first.result(timeout=2)
    def test_capacity_is_bounded(self):
        with patch.dict(q._PENDING,{str(i):Future() for i in range(q.MAX_PENDING)},clear=True):
            self.assertEqual(q.run('fifth',lambda i:{})['quoteFailureCode'],'PRODUCT_CAPACITY')

    def test_completed_timeout_result_is_delivered_without_refetch(self):
        f=Future();f.set_result({'isin':'late','quoteAt':'original'})
        with patch.dict(q._PENDING,{'late':f},clear=True):
            def forbidden(_):raise AssertionError('unnecessary second source request')
            first=q.run('late',forbidden)
            self.assertEqual(first['quoteAt'],'original')
            first['quoteAt']='modified'
            self.assertEqual(q.run('late',forbidden)['quoteAt'],'original')

    def test_four_busy_workers_do_not_reject_fifth_product(self):
        release=threading.Event()
        pending={str(i):Future() for i in range(4)}
        with patch.dict(q._PENDING,pending,clear=True):
            result=q.run('fifth',lambda isin:dict(isin=isin))
            self.assertEqual(result,{'isin':'fifth'})
