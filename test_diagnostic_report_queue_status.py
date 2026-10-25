"""Goal 17: report admission counters are read-only, bounded and private."""
import json
import threading
import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch

import report_admission as gate
import bob_diagnostics


def counters():
    return dict(completed=0, failed=0, capacityTimeouts=0,
                queueFull=0, joined=0, joiningTimeouts=0)


class ReportQueueStatusTests(unittest.TestCase):
    def test_status_read_only_no_keys_or_payload_or_credentials(self):
        future = Future()
        with patch.object(gate, '_pending', {'secret-report-query-123': future}), \
             patch.object(gate, '_COUNTERS', counters()):
            snapshot = gate.status()
        self.assertTrue(snapshot['readOnly'])
        self.assertFalse(snapshot['realOrders'])
        self.assertEqual(snapshot['pendingKeys'], 1)
        self.assertEqual(snapshot['maxActiveLoads'], 2)
        self.assertEqual(snapshot['maxPendingKeys'], 32)
        self.assertNotIn('secret-report', json.dumps(snapshot))
        self.assertNotIn('token', json.dumps(snapshot))
        self.assertIn('process', snapshot['scope'])

    def test_reports_observed_completion_but_not_last_user_receipt(self):
        with patch.object(gate, '_pending', {}), \
             patch.object(gate, '_COUNTERS', counters()):
            self.assertEqual(gate.read('health', lambda: {'ok': True}), {'ok': True})
            snapshot = gate.status()
        self.assertEqual(snapshot['completed'], 1)
        self.assertEqual(snapshot['activeLoads'], 0)
        self.assertEqual(snapshot['pendingKeys'], 0)
        self.assertNotIn('deliveryConfirmed', snapshot)

    def test_full_pending_registry_rejects_and_counts_without_keys(self):
        private = {'secret-'+str(i): Future() for i in range(32)}
        with patch.object(gate, '_pending', private), \
             patch.object(gate, '_COUNTERS', counters()):
            with self.assertRaisesRegex(TimeoutError, 'queue full'):
                gate.read('new-private-request', lambda: None)
            state = gate.status()
        self.assertEqual(state['pendingKeys'], 32)
        self.assertEqual(state['queueFull'], 1)
        self.assertNotIn('secret-', json.dumps(state))
        self.assertNotIn('new-private-request', json.dumps(state))

    def test_capacity_timeout_is_separate_from_loader_failure(self):
        slots=Mock()
        slots.acquire.return_value=False
        with patch.object(gate, '_pending', {}), \
             patch.object(gate, '_COUNTERS', counters()), \
             patch.object(gate, '_slots', slots):
            with self.assertRaisesRegex(TimeoutError, 'capacity'):
                gate.read('bounded', lambda: None)
            result=gate.status()
        self.assertEqual(result['capacityTimeouts'], 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['activeLoads'], 0)
        self.assertEqual(result['pendingKeys'], 0)
        slots.release.assert_not_called()

    def test_joined_read_does_not_consume_new_loader_slot(self):
        done=Future()
        done.set_result({'items':[1]})
        loader=Mock(side_effect=AssertionError('follower must not load'))
        with patch.object(gate, '_pending', {'secret-key': done}), \
             patch.object(gate, '_COUNTERS', counters()):
            copied=gate.read('secret-key', loader)
            state=gate.status()
        self.assertEqual(copied, {'items':[1]})
        self.assertEqual(state['joined'], 1)
        self.assertEqual(state['activeLoads'], 0)
        loader.assert_not_called()

    def test_private_push_snapshot_includes_only_safe_queue_counts(self):
        conn=Mock()
        conn.execute.return_value.fetchone.return_value=(0, 0)
        evaluator=Mock()
        evaluator.status.return_value={'completed':4,'queueTimeouts':0,'token':'DO_NOT_LEAK'}
        paper=Mock()
        paper.snapshot.return_value={'state':'paused'}
        policies=Mock(POLICIES=[])
        with patch.object(gate, '_pending', {}), \
             patch.object(gate, '_COUNTERS', counters()):
            result=bob_diagnostics.push_snapshot(conn,evaluator,paper,policies)
        self.assertEqual(result['reportAdmission']['pendingKeys'],0)
        self.assertTrue(result['reportAdmission']['readOnly'])
        self.assertFalse(result['reportAdmission']['realOrders'])
        self.assertNotIn('DO_NOT_LEAK',json.dumps(result))
        self.assertEqual(result['push']['deliveryStatus'],'not-verified')
        self.assertEqual(result['push']['evaluator']['completed'],4)
        self.assertNotIn('reportAdmission',result['push'])

    def test_loader_error_never_leaks_in_status(self):
        def leak():
            raise RuntimeError('PRIVATE_ACCOUNT_SECRET')
        with patch.object(gate, '_pending', {}), \
             patch.object(gate, '_COUNTERS', counters()):
            with self.assertRaises(RuntimeError):
                gate.read('secret-report-key', leak)
            state=gate.status()
        self.assertEqual(state['failed'],1)
        self.assertEqual(state['pendingKeys'],0)
        self.assertNotIn('PRIVATE_ACCOUNT_SECRET',json.dumps(state))


if __name__ == '__main__':
    unittest.main()
