import threading
import unittest
from concurrent.futures import Future
from unittest.mock import patch
import quote_runtime as q

class QuoteRuntimeTests(unittest.TestCase):
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
        with patch.dict(q._PENDING,{str(i):Future() for i in range(4)},clear=True):
            self.assertEqual(q.run('fifth',lambda i:{})['quoteFailureCode'],'PRODUCT_CAPACITY')
