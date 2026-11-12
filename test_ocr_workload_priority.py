import threading
import unittest
from unittest.mock import patch
import ocr_workload_priority as gate


class PriorityTests(unittest.TestCase):
    def test_optional_work_waits_then_resumes_without_loss(self):
        entered=threading.Event();finished=threading.Event()
        @gate.maintenance
        def task():
            entered.set();finished.set()
        with gate.ocr_slot():
            thread=threading.Thread(target=task);thread.start()
            self.assertFalse(entered.wait(.05))
            self.assertTrue(gate.status()['maintenancePaused'])
        self.assertTrue(finished.wait(2));thread.join(2)
        self.assertFalse(gate.status()['maintenancePaused'])

    def test_busy_maintenance_is_not_killed_and_ocr_is_bounded(self):
        with gate.maintenance_slot():
            with self.assertRaises(gate.OcrWorkloadDeferred):
                with gate.ocr_slot(timeout=.01):
                    self.fail('OCR overlapped running maintenance')
            self.assertEqual(gate.status()['maintenanceRunning'],1)
            self.assertEqual(gate.status()['ocrWaiting'],0)
        with gate.ocr_slot(timeout=.01):
            self.assertTrue(gate.status()['ocrActive'])

    def test_exceptions_release_both_sides(self):
        with self.assertRaises(ValueError):
            with gate.ocr_slot():raise ValueError()
        @gate.maintenance
        def fail():raise ValueError()
        with self.assertRaises(ValueError):fail()
        self.assertEqual(gate.status(),{'ocrActive':False,'ocrWaiting':0,
            'maintenanceRunning':0,'maintenancePaused':False})

    def test_existing_work_drains_before_ocr_and_new_work_cannot_jump_queue(self):
        requested=threading.Event();entered=threading.Event();release=threading.Event()
        def reader():
            requested.set()
            with gate.ocr_slot(timeout=2):
                entered.set();release.wait(2)
        with gate.maintenance_slot():
            thread=threading.Thread(target=reader);thread.start()
            self.assertTrue(requested.wait(1))
            self.assertFalse(entered.wait(.05))
        try:self.assertTrue(entered.wait(1))
        finally:release.set();thread.join(2)

    def test_handset_gate_precedes_evaluator_and_releases_on_failure(self):
        import handset_list_worker as worker
        def processing(*args,**kwargs):
            self.assertTrue(gate.status()['ocrActive'])
            raise ValueError('parse failed')
        with patch.object(worker,'_process',side_effect=processing):
            with self.assertRaises(ValueError):worker.process({'images':[]},'now')
        self.assertFalse(gate.status()['ocrActive'])

    def test_nested_maintenance_counts_once_and_unwinds(self):
        with gate.maintenance_slot():
            with gate.maintenance_slot():
                self.assertEqual(gate.status()['maintenanceRunning'],1)
        self.assertEqual(gate.status()['maintenanceRunning'],0)
