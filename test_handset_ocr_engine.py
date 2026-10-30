import sys
import types
import unittest
from unittest.mock import patch
import handset_ocr_engine

class EngineTests(unittest.TestCase):
    def test_small_session_options_and_restoration_on_success_or_failure(self):
        class Session:
            @staticmethod
            def _init_sess_opts(config):
                return types.SimpleNamespace(enable_cpu_mem_arena=False,threads=config['threads'])
        original=Session.__dict__['_init_sess_opts']
        modules={'onnxruntime':types.SimpleNamespace(GraphOptimizationLevel=types.SimpleNamespace(ORT_ENABLE_BASIC='basic')),
                 'rapidocr_onnxruntime.utils':types.SimpleNamespace(OrtInferSession=Session)}
        for fail in (False,True):
            def create():
                opt=Session._init_sess_opts({'threads':1})
                self.assertEqual(opt.graph_optimization_level,'basic')
                self.assertFalse(opt.enable_mem_pattern)
                self.assertFalse(opt.enable_cpu_mem_arena)
                self.assertEqual(opt.threads,1)
                if fail:raise RuntimeError('engine unavailable')
                return 'engine'
            with patch.dict(sys.modules,modules),patch('video_ocr.offline_engine',side_effect=create):
                if fail:
                    with self.assertRaises(RuntimeError):handset_ocr_engine.offline_engine()
                else:self.assertEqual(handset_ocr_engine.offline_engine(),'engine')
            self.assertIs(Session.__dict__['_init_sess_opts'],original)
