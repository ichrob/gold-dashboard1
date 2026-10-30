import threading
import unittest
from unittest.mock import Mock, patch
from background_handoff import LatestWorker


class BackgroundHandoffTests(unittest.TestCase):
    def test_slow_evaluation_does_not_block_input_delivery_and_only_newest_waits(self):
        worker = LatestWorker()
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        processed, delivered = [], []
        def process(bundle):
            processed.append(bundle['fetched_at'])
            if len(processed) == 1:
                started.set()
                self.assertTrue(release.wait(3))
            else:
                finished.set()
        first = {'fetched_at': 1, 'spots': {'xaus': 4000}}
        try:
            self.assertTrue(worker.submit(first, process, lambda b: delivered.append(b['fetched_at'])))
            self.assertTrue(started.wait(1))
            first['spots']['xaus'] = 1
            worker.submit({'fetched_at':2}, process, lambda b: delivered.append(b['fetched_at']))
            worker.submit({'fetched_at':3}, process, lambda b: delivered.append(b['fetched_at']))
            self.assertEqual(delivered, [1,2,3])
            self.assertEqual(processed, [1])
            self.assertTrue(worker.status()['pending'])
            self.assertEqual(worker.status()['coalesced'], 1)
            self.assertFalse(worker.submit({'fetched_at':2}, process, lambda b: delivered.append(2)))
            self.assertEqual(delivered, [1,2,3])
        finally:
            release.set()
        self.assertTrue(finished.wait(2))
        if worker.thread: worker.thread.join(2)
        self.assertEqual(processed, [1,3])
        self.assertEqual(worker.status()['completed'], 2)

    def test_error_is_visible_and_worker_recovers_without_leaking_error_text(self):
        worker = LatestWorker()
        worker.submit({'fetched_at':1}, Mock(side_effect=ValueError('private detail')))
        thread = worker.thread
        if thread: thread.join(2)
        self.assertEqual(worker.status()['failed'], 1)
        self.assertEqual(worker.status()['lastError'], 'ValueError')
        self.assertNotIn('private', str(worker.status()))
        called = Mock()
        worker.submit({'fetched_at':2}, called)
        thread = worker.thread
        if thread: thread.join(2)
        called.assert_called_once_with({'fetched_at':2})
        self.assertEqual(worker.status()['completed'], 1)
        self.assertIsNone(worker.status()['lastError'])

    def test_delivery_failure_is_not_acknowledged_or_evaluated(self):
        worker, process = LatestWorker(), Mock()
        with self.assertRaises(RuntimeError):
            worker.submit({}, process, Mock(side_effect=RuntimeError('enqueue failed')))
        self.assertEqual(worker.status()['accepted'], 0)
        process.assert_not_called()

    def test_input_copy_preserves_observation_clock(self):
        worker, done = LatestWorker(), threading.Event()
        original = {'fetched_at':1,'spots':{'spot_price_as_of':'original'}}
        def process(b):
            self.assertEqual(b, original)
            b['spots']['spot_price_as_of']='modified'
            done.set()
        worker.submit(original, process)
        self.assertTrue(done.wait(2))
        self.assertEqual(original['spots']['spot_price_as_of'], 'original')

    def test_delivery_keeps_every_existing_consumer(self):
        import push_server
        bundle = {'fetched_at':1}
        with patch('paper_simulation.enqueue') as paper, \
             patch('trade_auto_monitor.enqueue') as trade, \
             patch('product_comparison_worker.enqueue') as comparison, \
             patch('manual_paper_watch.enqueue') as manual, \
             patch.object(push_server, 'run_background') as evaluate:
            push_server.deliver_background_inputs(bundle)
        paper.assert_called_once_with(bundle, push_server.db)
        trade.assert_called_once_with(push_server.db, bundle)
        comparison.assert_called_once_with(push_server.db, bundle)
        manual.assert_called_once_with(push_server.db)
        evaluate.assert_not_called()

    def test_http_acknowledges_new_data_while_previous_evaluation_is_blocked(self):
        import http.client
        import json
        import push_server
        from http.server import ThreadingHTTPServer
        worker = LatestWorker()
        release, started = threading.Event(), threading.Event()
        delivered = []
        def process(bundle):
            started.set()
            release.wait(3)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), push_server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(push_server, 'PUSH_SERVICE_TOKEN', 'fixture-token'), \
                 patch.object(push_server.background_handoff, 'worker', worker), \
                 patch.object(push_server, 'run_background', side_effect=process), \
                 patch.object(push_server, 'deliver_background_inputs', side_effect=lambda b: delivered.append(b)):
                def post(at, token):
                    conn = http.client.HTTPConnection(*httpd.server_address, timeout=1)
                    conn.request('POST', '/background', json.dumps({'bundle':{'fetched_at':at}}),
                        {'Content-Type':'application/json', 'X-Bob-Push-Token':token})
                    response = conn.getresponse()
                    status, result = response.status, json.loads(response.read())
                    conn.close()
                    return status, result
                self.assertEqual(post(0, 'wrong')[0], 401)
                self.assertEqual(delivered, [])
                status, result = post(1, 'fixture-token')
                self.assertEqual(status, 200)
                self.assertTrue(result['accepted'])
                self.assertIsNone(result['sent'])
                self.assertTrue(started.wait(1))
                self.assertTrue(post(2, 'fixture-token')[1]['accepted'])
                self.assertEqual([b['fetched_at'] for b in delivered], [1,2])
                self.assertFalse(post(1, 'fixture-token')[1]['accepted'])
        finally:
            release.set()
            if worker.thread: worker.thread.join(2)
            httpd.shutdown()
            httpd.server_close()
            thread.join(2)
