"""A newly cached bundle must not renew the source quote's lifetime."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import server


class LiveCacheAgeTests(unittest.TestCase):
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
