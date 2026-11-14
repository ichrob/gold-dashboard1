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


    def test_optional_jobs_are_serial_and_foreground_goes_first(self):
        """Queued maintenance must not jump in front of a waiting handset."""
        import time
        first_entered=threading.Event()
        release_first=threading.Event()
        second_entered=threading.Event()
        foreground_entered=threading.Event()
        release_foreground=threading.Event()

        @gate.maintenance
        def first():
            first_entered.set()
            release_first.wait(3)

        @gate.maintenance
        def second():
            second_entered.set()

        def foreground():
            with gate.ocr_slot(timeout=2):
                foreground_entered.set()
                release_foreground.wait(2)

        a=threading.Thread(target=first)
        b=threading.Thread(target=second)
        c=threading.Thread(target=foreground)
        try:
            a.start()
            self.assertTrue(first_entered.wait(1))
            b.start()
            self.assertFalse(second_entered.wait(.05))
            self.assertEqual(gate.status()['maintenanceRunning'], 1)
            c.start()
            deadline=time.monotonic()+1
            while gate.status()['ocrWaiting'] != 1 and time.monotonic()<deadline:
                time.sleep(.005)
            self.assertEqual(gate.status()['ocrWaiting'], 1)
            release_first.set()
            self.assertTrue(foreground_entered.wait(1))
            self.assertFalse(second_entered.is_set())
            release_foreground.set()
            self.assertTrue(second_entered.wait(2))
        finally:
            release_first.set()
            release_foreground.set()
            for thread in (a,b,c):
                if thread.ident is not None:
                    thread.join(3)
        self.assertEqual(gate.status()['maintenanceRunning'], 0)
        self.assertFalse(gate.status()['ocrActive'])

    def test_storage_maintenance_respects_existing_foreground_gate(self):
        import storage_maintenance
        class Connection:
            autocommit=True
            def __init__(self):
                self.called=False
            def __enter__(self):
                self.called=True
                return self
            def __exit__(self, *args):
                return None
            def execute(self, sql, params=None):
                return self
            def fetchone(self):
                return (False,)
        conn=Connection()
        finished=threading.Event()
        def optional():
            storage_maintenance.run_once(lambda:conn)
            finished.set()
        with gate.ocr_slot():
            thread=threading.Thread(target=optional)
            thread.start()
            self.assertFalse(finished.wait(.05))
            self.assertFalse(conn.called)
        self.assertTrue(finished.wait(2))
        thread.join(2)
        self.assertTrue(conn.called)
