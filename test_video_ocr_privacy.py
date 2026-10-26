"""No real model initialization or external requests in these ordering tests."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import video_ocr


class OfflineEnginePrivacyTests(unittest.TestCase):
    def test_disable_telemetry_before_creating_model_sessions(self):
        events = []
        engine = object()
        disable = Mock(side_effect=lambda: events.append('disabled'))
        create = Mock(side_effect=lambda **kw: (events.append('created'), engine)[1])
        with patch.dict(sys.modules, {
            'onnxruntime': SimpleNamespace(disable_telemetry_events=disable),
            'rapidocr_onnxruntime': SimpleNamespace(RapidOCR=create),
        }):
            self.assertIs(video_ocr.offline_engine(), engine)
        self.assertEqual(events, ['disabled', 'created'])
        create.assert_called_once_with(intra_op_num_threads=1,
            inter_op_num_threads=1, det_limit_side_len=640, rec_batch_num=1)

    def test_failed_opt_out_does_not_start_engine(self):
        create = Mock()
        with patch.dict(sys.modules, {
            'onnxruntime': SimpleNamespace(disable_telemetry_events=Mock(
                side_effect=RuntimeError('opt-out unavailable'))),
            'rapidocr_onnxruntime': SimpleNamespace(RapidOCR=create),
        }):
            with self.assertRaises(RuntimeError):
                video_ocr.offline_engine()
        create.assert_not_called()

    def test_cover_only_input_does_not_initialize_runtime(self):
        with patch.object(video_ocr, 'offline_engine') as create:
            self.assertEqual(video_ocr.recognize([{'isCover': True}])['status'],
                             'no-timed-images')
        create.assert_not_called()
