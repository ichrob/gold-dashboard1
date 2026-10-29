import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, Future
from unittest.mock import Mock, patch
import report_admission as gate

class AdmissionTests(unittest.TestCase):
    def test_overlapping_read_uses_one_loader_and_returns_independent_values(self):
        barrier=threading.Barrier(8)
        start=threading.Barrier(8)
        class JoiningFuture(Future):
            def result(self,timeout=None):
                barrier.wait(timeout=5)
                return super().result(timeout)
        def loader():
            barrier.wait(timeout=5)
            return {'items':[1]}
        load=Mock(side_effect=loader)
        def call(_):start.wait(timeout=5);return gate.read('same',load)
        with patch.object(gate,'Future',JoiningFuture),ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(call,range(8)))
        self.assertEqual(load.call_count,1)
        results[0]['items'].append(2)
        self.assertEqual(results[1]['items'],[1])
        self.assertFalse(gate._pending)
        self.assertEqual(gate.read('same',lambda:{'new':True}),{'new':True})
    def test_copy_failure_is_shared_without_false_success_or_masked_error(self):
        joined=threading.Event()
        class JoiningFuture(Future):
            def result(self, timeout=None):
                joined.set()
                return super().result(timeout)
        class Uncopyable:
            def __deepcopy__(self, memo):
                raise ValueError('report-copy-failed')
        entered=threading.Event()
        def loader():
            entered.set()
            if not joined.wait(5):
                raise AssertionError('follower did not join')
            return Uncopyable()
        counters=dict(completed=0, failed=0, capacityTimeouts=0,
                      queueFull=0, joined=0, joiningTimeouts=0)
        with patch.object(gate, 'Future', JoiningFuture), \
             patch.object(gate, '_COUNTERS', counters), \
             ThreadPoolExecutor(max_workers=2) as pool:
            owner=pool.submit(gate.read, 'copy-error', loader)
            self.assertTrue(entered.wait(5))
            follower=pool.submit(gate.read, 'copy-error', Mock(side_effect=AssertionError('second loader')))
            for result in (owner, follower):
                with self.assertRaisesRegex(ValueError, 'report-copy-failed'):
                    result.result(5)
            self.assertEqual(gate.status()['completed'], 0)
            self.assertEqual(gate.status()['failed'], 1)
            self.assertEqual(gate.status()['activeLoads'], 0)
            self.assertEqual(gate.status()['pendingKeys'], 0)
            self.assertEqual(gate.read('copy-error', lambda: {'ok':True}), {'ok':True})

    def test_waiter_does_not_borrow_connection(self):
        entered=threading.Event();semaphore=threading.BoundedSemaphore(2)
        semaphore.acquire();semaphore.acquire()
        class ObservedSlots:
            def acquire(self,timeout):entered.set();return semaphore.acquire(timeout=timeout)
            def release(self):semaphore.release()
        loader=Mock(return_value={'ok':True})
        with patch.object(gate,'_slots',ObservedSlots()),ThreadPoolExecutor(max_workers=1) as pool:
            result=pool.submit(gate.read,'blocked',loader)
            self.assertTrue(entered.wait(5))
            loader.assert_not_called()
            semaphore.release()
            self.assertEqual(result.result(5),{'ok':True})
        semaphore.release()
    def test_failure_and_admission_timeout_release_state(self):
        with self.assertRaises(ValueError):gate.read('bad',lambda:(_ for _ in ()).throw(ValueError('test')))
        self.assertFalse(gate._pending)
        slots=Mock();slots.acquire.return_value=False;loader=Mock()
        with patch.object(gate,'_slots',slots),self.assertRaises(TimeoutError):gate.read('full',loader)
        loader.assert_not_called();slots.release.assert_not_called()
        self.assertFalse(gate._pending)
    def test_audit_keys_include_parameters_and_acquisition_is_inside_gate(self):
        import push_server
        with patch.object(push_server,'db') as db,patch.object(gate,'read',return_value={'ok':True}) as read:
            push_server.read_audit_report({'mode':'simulation','day':'2026-10-20'})
            first=read.call_args.args[0]
            push_server.read_audit_report({'mode':'simulation','day':'2026-10-19'})
            self.assertNotEqual(first,read.call_args.args[0]);db.assert_not_called()
            push_server.read_improvement_report();db.assert_not_called()

    def test_dashboard_reads_are_admitted_before_borrowing_connections(self):
        import push_server
        readers=[
            ('/product-audit', 'GET', None, 'product-audit'),
            ('/candidate-proofs', 'GET', None, 'candidate-proofs'),
            ('/risk-paper', 'GET', None, 'risk-paper'),
            ('/android-diagnostic-status', 'GET', None, 'android-diagnostic-status'),
            ('/android-read-status', 'GET', None, 'android-read-status'),
            ('/storage-health', 'GET', None, 'storage-health'),
            ('/diagnostics', 'GET', None, 'diagnostics'),
            ('/simulation-status', 'GET', None, 'simulation-status'),
            ('/comparison-status', 'GET', None, 'comparison-status'),
            ('/monitor-status', 'GET', None, 'monitor-status'),
            ('/email-import/read', 'POST', {}, 'email-import'),
            ('/list-correction', 'POST', {'action':'read'}, 'list-correction'),
        ]
        for path,method,payload,key in readers:
            with self.subTest(path=path):
                handler=object.__new__(push_server.Handler)
                handler.path=path
                handler.headers={'X-Bob-Push-Token':'test'}
                with patch.object(push_server,'PUSH_SERVICE_TOKEN','test'), \
                     patch.object(push_server,'json_body',return_value=payload), \
                     patch.object(push_server,'read_db_report',return_value={'ok':True}) as admitted, \
                     patch.object(push_server,'db') as db, \
                     patch.object(push_server,'send_json') as send:
                    getattr(handler,'do_'+method)()
                admitted.assert_called_once()
                self.assertEqual(admitted.call_args.args[0],key)
                db.assert_not_called()
                self.assertEqual(send.call_args.args[1],200)

    def test_parameterized_history_reads_use_distinct_admission_keys(self):
        import push_server
        for route in ('push-delivery-history', 'signal-history'):
            keys=[]
            for offset in (0, 100):
                handler=object.__new__(push_server.Handler)
                handler.path=f'/{route}?offset={offset}'
                handler.headers={'X-Bob-Push-Token':'test'}
                with patch.object(push_server,'PUSH_SERVICE_TOKEN','test'), \
                     patch.object(push_server,'read_db_report',return_value={'ok':True}) as admitted, \
                     patch.object(push_server,'db') as db, \
                     patch.object(push_server,'send_json') as send:
                    handler.do_GET()
                keys.append(admitted.call_args.args[0])
                self.assertTrue(keys[-1].startswith(route+':'))
                db.assert_not_called()
                self.assertEqual(send.call_args.args[1],200)
            self.assertNotEqual(keys[0],keys[1])

    def test_video_read_is_admitted_but_write_bypasses_read_gate(self):
        import push_server
        import video_evidence
        handler=object.__new__(push_server.Handler)
        handler.path='/research-video/evidence'
        handler.headers={'X-Bob-Push-Token':'test'}
        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test'), \
             patch.object(push_server,'json_body',return_value={'videoId':'abcdefghijk','action':'read'}), \
             patch.object(gate,'read',return_value={'frames':[]}) as admitted, \
             patch.object(push_server,'db') as db, \
             patch.object(push_server,'send_json'):
            handler.do_POST()
        admitted.assert_called_once()
        self.assertTrue(admitted.call_args.args[0].startswith('video-evidence:'))
        db.assert_not_called()

        with patch.object(push_server,'PUSH_SERVICE_TOKEN','test'), \
             patch.object(push_server,'json_body',return_value={'videoId':'abcdefghijk','action':'write'}), \
             patch.object(push_server,'read_video_evidence',side_effect=AssertionError('write entered read gate')), \
             patch.object(video_evidence,'handle',return_value={'ok':True}) as write, \
             patch.object(push_server,'send_json'):
            handler.do_POST()
        write.assert_called_once()
if __name__=='__main__':unittest.main()
