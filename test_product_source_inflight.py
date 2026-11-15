"""Same-ISIN issuer lookups do not multiply source requests or fake proof."""
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import product_source_recovery as recovery
import product_repair_learning as learning


class InflightProductSourceTests(unittest.TestCase):
    def setUp(self):
        with recovery._LOCK:
            recovery._FAILURES.clear()
            recovery._SOURCE_FAILURES.clear()
            recovery._SOURCE_PAUSES.clear()
            recovery._INFLIGHT.clear()

    def test_same_stage_and_isin_is_bounded_nonblocking_and_fail_closed(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        first_events = []
        def slow():
            calls.append("first")
            entered.set()
            if not release.wait(timeout=4):
                raise TimeoutError("synthetic first request timed out")
            return {'isin': 'SYNTHETIC', 'bidAt': 'source-original-time'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(recovery.attempt, 'comdirect-fetch', 'SYNTHETIC',
                                slow, {}, first_events, now=100)
            self.assertTrue(entered.wait(timeout=2))
            second_events = []
            # The suppressed reader must not wait for the slow provider and
            # must not be given a fabricated quote.
            other = recovery.attempt('comdirect-fetch','SYNTHETIC',
                    lambda: self.fail('duplicate provider fetch'), {}, second_events,
                    now=100.1)
            self.assertEqual(other,{})
            self.assertEqual(second_events,[{'stage':'comdirect-fetch',
                 'state':'waiting','scope':'inflight','retryAfterSeconds':1}])
            self.assertEqual(len(calls),1)
            release.set()
            observed=first.result(timeout=3)
            self.assertEqual(observed['bidAt'],'source-original-time')
        self.assertFalse(recovery._INFLIGHT)
        self.assertFalse(recovery._FAILURES)
        self.assertEqual(first_events,[])
        distinct=recovery.attempt('comdirect-fetch','SYNTHETIC',
                                  lambda:{'state':'new-original'}, {}, [], now=102)
        self.assertEqual(distinct,{'state':'new-original'})

    def test_failed_adapter_releases_inflight_without_erasing_backoff(self):
        events=[]
        def failed():
            raise OSError('PRIVATE SOURCE ERROR')
        result=recovery.attempt('swissquote-fetch','SYNTHETIC',
                                failed,{'safe':True},events,now=10)
        self.assertEqual(result,{'safe':True})
        self.assertEqual(events[-1]['state'],'failed')
        self.assertFalse(recovery._INFLIGHT)
        self.assertIn(('swissquote-fetch','SYNTHETIC'),recovery._FAILURES)
        events=[]
        result=recovery.attempt('swissquote-fetch','SYNTHETIC',
                                lambda:{'restored':True}, {}, events,now=40)
        self.assertEqual(result,{'restored':True})
        self.assertEqual(events[-1]['state'],'call-restored')
        self.assertFalse(recovery._FAILURES)
        self.assertNotIn('PRIVATE SOURCE ERROR',str(events))

    def test_independent_products_and_adapters_continue_in_parallel(self):
        entered, release=threading.Event(),threading.Event()
        def slow():
            entered.set()
            if not release.wait(timeout=4):
                raise TimeoutError('fixture only')
            return {'state':'done'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(recovery.attempt,'comdirect-fetch','P1',
                              slow,{},[],now=3)
            self.assertTrue(entered.wait(timeout=2))
            a=recovery.attempt('comdirect-fetch','P2',lambda:{'other':True}, {},[],now=3)
            b=recovery.attempt('swissquote-fetch','P1',lambda:{'otherStage':True},
                               {},[],now=3)
            self.assertEqual(a,{'other':True})
            self.assertEqual(b,{'otherStage':True})
            release.set()
            self.assertEqual(first.result(timeout=3),{'state':'done'})
        self.assertFalse(recovery._INFLIGHT)

    def test_duplicate_waiting_does_not_penalize_source_reputation(self):
        now=1794648000000
        t=datetime.fromtimestamp(now/1000,timezone.utc).isoformat()
        item={'state':'incomplete','missing':['quote'],
              'sourceRecovery':[{'stage':'comdirect-fetch','state':'waiting',
                                 'scope':'inflight','retryAfterSeconds':1}],
              'quoteSourceAt':t,'dataQuoteSource':'comdirect'}
        previous={'repairLearning':{'sourceSuccesses':
                  {'comdirect':4,'swissquote':2}}}
        r=learning.update(item,previous,now)
        self.assertEqual(r['sourceSuccesses']['comdirect'],4)
        self.assertEqual(r['failedSources'],[])
        self.assertEqual(r['incidents']['quotes']['state'],'repairing')
        # A real rate-limit/source cooldown is still counted as unresolved.
        item['sourceRecovery'][0]['scope']='source'
        r=learning.update(item,previous,now)
        self.assertEqual(r['failedSources'],['comdirect'])
        self.assertEqual(r['sourceSuccesses']['comdirect'],3)


if __name__=='__main__':
    unittest.main()
