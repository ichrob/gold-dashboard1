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

    def test_completed_result_ttl_starts_at_completion(self):
        f=Future();f.set_result({'isin':'late','quoteAt':'original'})
        f._bob_completed_at=100
        with patch.dict(q._PENDING,{'late':f},clear=True),patch.object(q.time,'monotonic',return_value=110):
            first=q.run('late',lambda _:self.fail('unnecessary fetch'))
            self.assertEqual(first['quoteAt'],'original')
            self.assertEqual(q._READY['late'][0],100+q.RESULT_TTL)

    def test_expired_uncollected_results_are_refetched(self):
        for result in ({'quoteAt':'stale'},q.unavailable('late','PRODUCT_SOURCE_FAILED')):
            f=Future();f.set_result(result);f._bob_completed_at=100
            with self.subTest(result=result),patch.dict(q._PENDING,{'late':f},clear=True),patch.object(q.time,'monotonic',return_value=1000):
                self.assertEqual(q.run('late',lambda _: {'quoteAt':'fresh'}),{'quoteAt':'fresh'})
