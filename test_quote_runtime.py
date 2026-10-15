import threading
import unittest
from concurrent.futures import Future
from unittest.mock import patch
import quote_runtime as q

class QuoteRuntimeTests(unittest.TestCase):
    def setUp(self):
        for name in ('_READY', '_RETAINED'):
            patcher=patch.object(q,name,q.OrderedDict())
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


    def test_late_verified_data_survives_fast_cache_expiry_as_unapproved_history(self):
        isin = 'DE000FG7N6Z2'
        verified = dict(isin=isin, productVerified=True, found=True, fresh=True,
                        eligible=True, bid=1.2, bidAt='2026-10-15T18:00:00+00:00',
                        metadata=dict(status=1, currency='EUR', ko=4000.0))
        finished = Future()
        finished.set_result(verified)
        finished._bob_completed_at = 100
        waiting = Future()
        with patch.dict(q._PENDING, {isin:finished}, clear=True), \
             patch.object(q._POOL, 'submit', return_value=waiting), \
             patch.object(q,'WAIT_SECONDS',.001), \
             patch.object(q.time,'monotonic',return_value=130):
            got = q.run(isin, lambda _ : self.fail('submission handled by stub'))
        self.assertTrue(got['productVerified'])
        self.assertEqual(got['metadata']['ko'],4000.0)
        self.assertEqual(got['bidAt'],verified['bidAt'])
        self.assertTrue(got['retainedAfterSourceFailure'])
        self.assertEqual(got['quoteFailureCode'],'PRODUCT_TIMEOUT')
        self.assertFalse(got['found'])
        self.assertFalse(got['fresh'])
        self.assertFalse(got['eligible'])
        self.assertFalse(got['isExecutableQuote'])

    def test_retention_never_converts_old_or_unverified_data_to_live(self):
        isin='DE000FG7N6Z2'
        old=dict(isin=isin,productVerified=True,found=True,eligible=True,
                 metadata=dict(status=1,ko=4400))
        q._RETAINED[isin]=(100,old)
        with patch.dict(q._PENDING, {str(i):Future() for i in range(q.MAX_PENDING)}, clear=True), \
             patch.object(q.time,'monotonic',return_value=100+q.RETENTION_SECONDS+1):
            got=q.run(isin,lambda _:self.fail('capacity reached'))
        self.assertEqual(got['quoteFailureCode'],'PRODUCT_CAPACITY')
        self.assertFalse(got['productVerified'])
        self.assertNotIn('metadata',got)
        self.assertNotIn(isin,q._RETAINED)

    def test_fresh_response_replaces_retained_source_without_refreshing_old_clock(self):
        isin='DE000FG7N6Z2'
        q._RETAINED[isin]=(100,dict(isin=isin,productVerified=True,found=True,
                                  metadata=dict(status=1,ko=4000)))
        current=dict(isin=isin,productVerified=True,found=True,eligible=False,
                     quoteAt='original-new-time',metadata=dict(status=2,ko=4100))
        with patch.dict(q._PENDING,{},clear=True):
            got=q.run(isin,lambda _:current)
        self.assertEqual(got['metadata']['status'],2)
        self.assertEqual(q._RETAINED[isin][1]['metadata']['ko'],4100)
        self.assertEqual(q._RETAINED[isin][1]['quoteAt'],'original-new-time')
