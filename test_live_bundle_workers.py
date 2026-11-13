"""Regression: slow live providers must not accumulate duplicate worker tasks."""
import ast
import threading
import unittest
from pathlib import Path

import live_bundle_workers


class LiveBundleWorkersTest(unittest.TestCase):
    def test_stalled_source_is_reused_without_queuing_duplicate_work(self):
        pool = live_bundle_workers.BoundedSourceExecutor()
        gate = threading.Event()
        begun = threading.Event()
        calls = []

        def slow():
            calls.append(1)
            begun.set()
            gate.wait(2)
            return "original-observation"

        try:
            first = pool.submit("5m", slow)
            self.assertTrue(begun.wait(1))
            for _ in range(100):
                self.assertIs(first, pool.submit("5m", slow))
            self.assertEqual(len(calls), 1)
            gate.set()
            self.assertEqual(first.result(timeout=2), "original-observation")
            second = pool.submit("5m", lambda: "new-observation")
            self.assertIsNot(first, second)
            self.assertEqual(second.result(timeout=2), "new-observation")
        finally:
            gate.set()
            pool.close()

    def test_at_most_one_pending_future_per_source_across_refresh_cycles(self):
        pool = live_bundle_workers.BoundedSourceExecutor()
        gate = threading.Event()
        started = threading.Event()
        lock = threading.Lock()
        calls = []
        try:
            def slow(name):
                with lock:
                    calls.append(name)
                    if len(calls) == len(live_bundle_workers.SOURCES):
                        started.set()
                gate.wait(2)
                return name

            original = {name:pool.submit(name, slow, name)
                        for name in live_bundle_workers.SOURCES}
            self.assertTrue(started.wait(1))
            for _ in range(20):
                for name in live_bundle_workers.SOURCES:
                    self.assertIs(pool.submit(name, slow, name), original[name])
            self.assertEqual(len(calls), len(live_bundle_workers.SOURCES))
            gate.set()
            for name, future in original.items():
                self.assertEqual(future.result(timeout=2), name)
        finally:
            gate.set()
            pool.close()

    def test_failure_does_not_permanently_poison_a_source(self):
        pool = live_bundle_workers.BoundedSourceExecutor()
        try:
            bad = pool.submit("fx", lambda: 1 / 0)
            with self.assertRaises(ZeroDivisionError):
                bad.result(timeout=2)
            good = pool.submit("fx", lambda: {"sourceAt": "unchanged"})
            self.assertEqual(good.result(timeout=2), {"sourceAt": "unchanged"})
            self.assertIsNot(bad, good)
            with self.assertRaises(ValueError):
                pool.submit("unknown", lambda: None)
        finally:
            pool.close()

    def test_scanner_uses_shared_source_workers_not_per_cycle_executor(self):
        source = Path(__file__).with_name("server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        builder = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                       and n.name == "build_live_bundle")
        block = ast.get_source_segment(source, builder)
        self.assertIn('live_bundle_workers.submit("spot", fetch_spot)', block)
        self.assertIn('live_bundle_workers.submit("5m", fetch_technical_history, "5m", "5d")', block)
        self.assertNotIn("ThreadPoolExecutor(", block)
        self.assertNotIn("shutdown(wait=False", block)
        # Keep the existing no-look-ahead source-clocks and risk safeguards.
        self.assertIn("recheck_spot_before_bundle", block)
        self.assertIn('0 <= goldprice_age <= 60', block)


if __name__ == "__main__":
    unittest.main()
