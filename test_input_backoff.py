import unittest
from unittest.mock import patch
import sg_quotes as s

class InputBackoffTests(unittest.TestCase):
    def test_outage_is_not_retried_for_every_product(self):
        with patch.dict(s._INPUT_CACHE,{},clear=True),patch.dict(s._INPUT_ERRORS,{},clear=True),patch('fx_data.fetch_rates',side_effect=OSError('offline')) as request:
            with self.assertRaises(OSError):s.market_input('fx')
            with self.assertRaises(ValueError):s.market_input('fx')
            self.assertEqual(request.call_count,1)

    def test_recovers_after_backoff(self):
        value={'data_updated_at':'original'}
        with patch.dict(s._INPUT_CACHE,{},clear=True),patch.dict(s._INPUT_ERRORS,{'fx':(0,'offline')},clear=True),patch.object(s.time,'monotonic',return_value=31),patch('fx_data.fetch_rates',return_value=value):
            self.assertEqual(s.market_input('fx'),value)
            self.assertNotIn('fx',s._INPUT_ERRORS)
