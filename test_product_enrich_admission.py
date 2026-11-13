import http.client
import threading
import unittest
from unittest.mock import patch

import product_enrich_admission as admission
import server


class ProductEnrichAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.original = admission._GATE
        admission._GATE = threading.BoundedSemaphore(admission.MAX_ACTIVE)
        self.addCleanup(setattr, admission, '_GATE', self.original)

    def test_concurrent_reads_are_bounded_without_a_waiting_queue(self):
        entered = []
        rejected = []
        release = threading.Event()
        lock = threading.Lock()

        def load(index):
            with lock:
                entered.append(index)
            release.wait(2)
            return index

        def call(index):
            try:
                admission.run(lambda: load(index))
            except admission.ProductEnrichBusy:
                with lock:
                    rejected.append(index)

        threads = [threading.Thread(target=call, args=(index,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for _ in range(200):
            with lock:
                if len(entered) + len(rejected) == len(threads):
                    break
            threading.Event().wait(.005)
        release.set()
        for thread in threads:
            thread.join(2)

        self.assertEqual(len(entered), admission.MAX_ACTIVE)
        self.assertEqual(len(rejected), len(threads) - admission.MAX_ACTIVE)
        self.assertEqual(admission.run(lambda: 'next'), 'next')

    def test_loader_error_releases_slot(self):
        with self.assertRaisesRegex(ValueError, 'source failed'):
            admission.run(lambda: (_ for _ in ()).throw(ValueError('source failed')))
        self.assertEqual(admission.run(lambda: 'recovered'), 'recovered')

    def test_terms_only_still_uses_the_direct_issuer_reader(self):
        isin = 'DE000FG4JXV7'
        with patch.dict(server.product_quotes.SG_DIRECT_PRODUCTS,
                        {isin: 'expected-product'}, clear=True), \
                patch('sg_direct.get_quote', return_value={'isin': isin}) as reader:
            self.assertEqual(server.enrich_degiro_product(isin, terms_only=True),
                             {'isin': isin})
        reader.assert_called_once_with(isin, terms_only=True)

    def test_http_route_returns_retryable_503_when_slots_are_busy(self):
        for _ in range(admission.MAX_ACTIVE):
            self.assertTrue(admission._GATE.acquire(blocking=False))
        self.addCleanup(lambda: [admission._GATE.release()
                                 for _ in range(admission.MAX_ACTIVE)])
        with server.BobHTTPServer(('127.0.0.1', 0), server.Handler) as httpd, \
                patch.object(server.Handler, 'authenticated', return_value=True):
            worker = threading.Thread(target=httpd.handle_request)
            worker.start()
            connection = http.client.HTTPConnection(*httpd.server_address, timeout=2)
            try:
                connection.request('GET', '/api/degiro/enrich?isin=DE000FG4JXV7')
                response = connection.getresponse()
                body = response.read()
            finally:
                connection.close()
                worker.join(2)
        self.assertEqual(response.status, 503)
        self.assertEqual(response.getheader('Retry-After'), '15')
        self.assertIn(b'"retryable":true', body)


if __name__ == '__main__':
    unittest.main()
