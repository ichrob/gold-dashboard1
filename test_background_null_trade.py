import unittest
from types import SimpleNamespace
from unittest.mock import patch

import background_push


class NullTradeAnalysisTest(unittest.TestCase):
    def test_analysis_accepts_no_trade_and_preserves_priority(self):
        for settings, override, expected in (
            ({'trade': None}, None, 1),
            ({}, None, 1),
            ({'trade': {'active': True}}, None, 0),
            ({'trade': None}, 2, 2),
        ):
            with self.subTest(settings=settings, override=override):
                with patch.object(background_push.evaluator_runtime, 'run',
                                  return_value=SimpleNamespace(returncode=0, stdout='{"ready":true,"priceFresh":true}')) as run:
                    result = background_push.analyze({}, settings, priority=override)
                    self.assertTrue(result['ready'])
                    self.assertEqual(run.call_args.kwargs['priority'], expected)


if __name__ == '__main__':
    unittest.main()
