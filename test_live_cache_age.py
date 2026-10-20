"""A newly cached bundle must not renew the source quote's lifetime."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import server


class LiveCacheAgeTests(unittest.TestCase):
    def test_new_confirmed_minute_bypasses_bundle_ttl_without_network_or_mutation(self):
        import copy
        now=1800000010
        latest=int(now//60)*60000-60000
        def row(at,**kw):return dict(openTime=at,isOpen=False,instrument='XAU/USD',source='test',**kw)
        bundle={'spots':{'spot_price_as_of':datetime.fromtimestamp(now-5,timezone.utc).isoformat()},
                'history':{'bars_by_tf':{'1m':[row(latest-60000)]}}}
        before=copy.deepcopy(bundle)
        with patch.object(server,'_live_cache',bundle),patch.object(server,'_live_cache_at',now-1), \
             patch.dict(server._technical_history,{'1m':[row(latest)]},clear=True), \
             patch.object(server,'fetch_json') as network:
            self.assertFalse(server.live_cache_reusable(now))
            self.assertEqual(bundle,before)
            network.assert_not_called()
            # No improved source evidence: keep normal cache/error backoff.
            server._technical_history['1m']=[row(latest-60000)]
            self.assertTrue(server.live_cache_reusable(now))
            server._technical_history['1m']=[dict(row(latest),isOpen=True)]
            self.assertTrue(server.live_cache_reusable(now))
            server._technical_history['1m']=[dict(row(latest),instrument='GC=F')]
            self.assertTrue(server.live_cache_reusable(now))

    def reusable(self, source_age, cache_age=1, error=None):
        now = 1791536000
        stamp = datetime.fromtimestamp(now-source_age, timezone.utc).isoformat()
        with patch.object(server, '_live_cache', {'spots': {
                'spot_price_as_of': stamp, 'spot_error': error}}), \
                patch.object(server, '_live_cache_at', now-cache_age):
            return server.live_cache_reusable(now)

    def test_source_clock_expires_before_bundle_ttl(self):
        self.assertTrue(self.reusable(29))
        self.assertFalse(self.reusable(30))
        self.assertFalse(self.reusable(59))
        self.assertFalse(self.reusable(61))
        self.assertFalse(self.reusable(-1))

    def test_bundle_ttl_and_provider_error_backoff_remain_bounded(self):
        self.assertFalse(self.reusable(1, cache_age=server.LIVE_CACHE_TTL))
        self.assertTrue(self.reusable(100, error='offline'))
        self.assertFalse(self.reusable(100, cache_age=server.LIVE_CACHE_TTL, error='offline'))
