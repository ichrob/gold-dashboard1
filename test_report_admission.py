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
if __name__=='__main__':unittest.main()
