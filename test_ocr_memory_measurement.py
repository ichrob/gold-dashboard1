import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

import handset_list_worker as w


class OcrMemoryMeasurementTests(unittest.TestCase):
    def test_peak_samples_do_not_change_success(self):
        child=Mock(returncode=0)
        child.poll.side_effect=[None,None,0]
        measurement={'beforeBytes':100,'peakBytes':100,'samples':0}
        result=w.wait_ocr(child,memory_reader=Mock(side_effect=[120,110]),
                          clock=lambda:0,sleep=lambda _:None,measurement=measurement)
        self.assertEqual(result,0)
        self.assertEqual(measurement,{'beforeBytes':100,'peakBytes':120,'samples':2})
        child.kill.assert_not_called()

    def test_memory_limit_still_kills_child_and_records_peak(self):
        child=Mock()
        child.poll.return_value=None
        measurement={'peakBytes':0,'samples':0}
        with self.assertRaises(MemoryError):
            w.wait_ocr(child,memory_reader=lambda:w.OCR_CONTAINER_LIMIT,
                       clock=lambda:0,measurement=measurement)
        child.kill.assert_called_once()
        self.assertEqual(measurement['peakBytes'],w.OCR_CONTAINER_LIMIT)

    def test_unknown_memory_and_timeout_remain_fail_closed(self):
        for memory,clock,error in [(None,lambda:0,RuntimeError),(1,Mock(side_effect=[0,121]),subprocess.TimeoutExpired)]:
            child=Mock();child.poll.return_value=None
            with self.assertRaises(error):
                w.wait_ocr(child,memory_reader=lambda:memory,clock=clock)
            child.kill.assert_called_once()

    def test_report_is_small_and_contains_only_measurements(self):
        out=io.StringIO()
        with patch.object(w,'container_memory_bytes',return_value=100*1024*1024),redirect_stdout(out):
            w.report_ocr_memory({'beforeBytes':90*1024*1024,'peakBytes':150*1024*1024,'samples':3},'completed',w.time.monotonic())
        report=json.loads(out.getvalue().split(' ',1)[1])
        self.assertEqual(report['sampledPeakMiB'],150)
        self.assertEqual(report['afterMiB'],100)
        self.assertEqual(report['samples'],3)
        self.assertEqual(set(report),{'scope','outcome','beforeMiB','sampledPeakMiB','afterMiB','samples','durationMs'})
        self.assertEqual(w.status()['lastOcrMemory'],report)

    def test_reporting_failure_does_not_interrupt_processing(self):
        with patch.object(w,'container_memory_bytes',side_effect=OSError):
            w.report_ocr_memory({'samples':0},'failed',w.time.monotonic())
