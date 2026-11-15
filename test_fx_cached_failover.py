import copy
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import sg_quotes
import fx_data


class CachedFxFailoverTests(unittest.TestCase):
    def test_expired_cached_fx_uses_ready_backup_without_network_or_redating(self):
        now = datetime.now(timezone.utc)
        def payload(seconds):
            at = (now-timedelta(seconds=seconds)).isoformat()
            return dict(result='success', base='USD', rates={'EUR':.9,'CHF':.8},
                        data_updated_at=at, effective_at={'EUR':at,'CHF':at},
                        sources={'EUR':'live','CHF':'live'}, source='live',
                        market_session='open', backupActive=True)
        old, ready = payload(100), payload(5)
        original = copy.deepcopy(ready)
        with patch.object(sg_quotes, '_INPUT_CACHE', {'fx':(100,old)}) as cache, \
             patch.object(sg_quotes.time, 'monotonic', return_value=101), \
             patch.object(fx_data, 'peek_backup', return_value=ready), \
             patch.object(fx_data, 'fetch_rates') as network:
            result = sg_quotes.market_input('fx')
            self.assertEqual(result, original)
            self.assertEqual(cache['fx'][0],100)
            network.assert_not_called()
            result['rates']['CHF'] = 999
            self.assertEqual(ready,original)

    def test_valid_primary_keeps_priority_and_unavailable_backup_keeps_clock(self):
        now = datetime.now(timezone.utc)
        for seconds in (5,100):
            at=(now-timedelta(seconds=seconds)).isoformat()
            old=dict(result='success',base='USD',rates={'EUR':.9,'CHF':.8},
                     data_updated_at=at,effective_at={'EUR':at,'CHF':at},
                     sources={'EUR':'live','CHF':'live'},market_session='open')
            with self.subTest(seconds=seconds), \
                 patch.object(sg_quotes,'_INPUT_CACHE',{'fx':(100,old)}), \
                 patch.object(sg_quotes.time,'monotonic',return_value=101), \
                 patch.object(fx_data,'peek_backup',return_value=None), \
                 patch.object(fx_data,'fetch_rates') as network:
                self.assertEqual(sg_quotes.market_input('fx'),old)
                network.assert_not_called()
