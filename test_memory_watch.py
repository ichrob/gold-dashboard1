import json
import unittest
from unittest.mock import patch

import memory_watch as m


class MemoryWatchTests(unittest.TestCase):
    def test_reclamation_requires_pressure_and_respects_cooldown(self):
        sample = dict(containerMiB=310, limitMiB=512, parentMiB=280)
        self.assertTrue(m.reclaim_due(sample, 240, 120))
        self.assertFalse(m.reclaim_due(sample, 239, 120))
        for field, value in [('containerMiB', 200), ('limitMiB', None),
                             ('parentMiB', None), ('parentMiB', 50)]:
            self.assertFalse(m.reclaim_due({**sample, field:value}, 500, 0))

    def test_native_reclaim_preserves_live_buffers(self):
        # Exercise the actual allocator interface while live data stays owned.
        import hashlib
        buffers = [bytearray(bytes([i]) * 131072) for i in range(16)]
        before = [hashlib.sha256(b).digest() for b in buffers]
        released = m.release_free_pages()
        self.assertIn(released, (None, False, True))
        self.assertEqual(before, [hashlib.sha256(b).digest() for b in buffers])

    def test_reclaim_unavailable_does_not_fail_worker(self):
        import ctypes
        with patch.object(ctypes, 'CDLL', return_value=object()):
            self.assertIsNone(m.release_free_pages())

    def test_watcher_reclaims_once_under_sustained_pressure(self):
        sample = dict(containerMiB=400, limitMiB=512, kernelPeakMiB=410,
                      parentMiB=380, childrenMiB=0, nodeMiB=0,
                      pythonChildrenMiB=0, children=0, threads=18)
        class Stop:
            cycles = 0
            def is_set(self): return self.cycles >= 3
            def wait(self, _):
                self.cycles += 1
                return self.cycles >= 3
        emitted = []
        with patch.object(m, 'snapshot', return_value=sample), \
             patch.object(m.time, 'monotonic', side_effect=[1000,1000,1000,1001,1002]), \
             patch.object(m, 'release_free_pages', return_value=True) as release:
            m.watch(stop=Stop(), interval=0, reclaim=True,
                    emit=lambda line, **_: emitted.append(line))
        release.assert_called_once()
        self.assertEqual(sum(s.startswith('BOB_MEMORY_RECLAIM ') for s in emitted), 1)

    def test_unavailable_process_details_are_safe(self):
        with patch.object(m, "_text", return_value=None):
            self.assertIsNone(m._number("/unavailable"))
            self.assertIsNone(m._rss(12345))
        self.assertIsNone(m._mib(None))

    def test_collects_node_and_python_separately_without_command_lines(self):
        sizes = {91: 90 * m._MIB, 92: 25 * m._MIB, 93: 15 * m._MIB, 42: 275 * m._MIB}
        readings = {
            "/sys/fs/cgroup/memory.current": 405 * m._MIB,
            "/sys/fs/cgroup/memory.max": 512 * m._MIB,
            "/sys/fs/cgroup/memory.peak": 475 * m._MIB,
        }
        programs = {91: "node", 92: "python", 93: "other"}
        with patch.object(m.os, "getpid", return_value=42), \
             patch.object(m, "_child_pids", return_value={91, 92, 93}), \
             patch.object(m, "_rss", side_effect=sizes.get), \
             patch.object(m, "_number", side_effect=lambda path: readings.get(path)), \
             patch.object(m, "_text", side_effect=lambda path: programs.get(int(path.split("/")[2])) if path.endswith("/comm") else None):
            sample = m.snapshot()
        self.assertEqual(sample["containerMiB"], 405.0)
        self.assertEqual(sample["limitMiB"], 512.0)
        self.assertEqual(sample["kernelPeakMiB"], 475.0)
        self.assertEqual(sample["parentMiB"], 275.0)
        self.assertEqual(sample["childrenMiB"], 130.0)
        self.assertEqual(sample["nodeMiB"], 90.0)
        self.assertEqual(sample["pythonChildrenMiB"], 25.0)
        self.assertEqual(sample["children"], 3)
        self.assertNotIn("cmdline", json.dumps(sample))

    def test_child_scan_deduplicates_all_thread_children(self):
        def data(path):
            if path.endswith("/10/children"):
                return "31 32"
            if path.endswith("/11/children"):
                return "32 33"
            return None
        with patch.object(m.os, "listdir", return_value=["10", "11", "bad"]), \
             patch.object(m, "_text", side_effect=data):
            self.assertEqual(m._child_pids(42), {31, 32, 33})

    def test_watch_throttles_high_memory_logs_without_payloads(self):
        sample = {
            "containerMiB": 490.0, "limitMiB": 512.0,
            "kernelPeakMiB": 495.0, "parentMiB": 330.0,
            "childrenMiB": 160.0, "nodeMiB": 140.0,
            "pythonChildrenMiB": 0.0, "children": 1, "threads": 7,
        }
        class Stop:
            cycles = 0
            def is_set(self):
                return self.cycles >= 3
            def wait(self, _):
                self.cycles += 1
                return self.cycles >= 3
        emitted = []
        def capture(line, **_):
            emitted.append(line)
        with patch.object(m, "snapshot", return_value=sample), \
             patch.object(m.time, "monotonic", side_effect=[1000.0, 1001.0, 1002.0]):
            m.watch(stop=Stop(), interval=0, emit=capture)
        self.assertEqual(len(emitted), 1)
        self.assertTrue(emitted[0].startswith("BOB_MEMORY "))
        data = json.loads(emitted[0].split(" ", 1)[1])
        self.assertEqual(data["observedNodeHighMiB"], 140.0)
        self.assertEqual(data["observedHighMiB"], 490.0)
        self.assertNotIn("payload", emitted[0])
        self.assertNotIn("token", emitted[0].lower())


if __name__ == "__main__":
    unittest.main()
