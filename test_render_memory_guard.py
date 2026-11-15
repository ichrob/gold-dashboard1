"""No-network regression for conservative Render PostgreSQL RAM gates."""
import datetime
import json
import os
import unittest
from unittest.mock import patch

import render_memory_guard as guard


class RenderMemoryGuardTests(unittest.TestCase):
    NOW = 2_000_000.0

    def series(self, amounts, *, unit='bytes', resource=guard.RESOURCE):
        return [{'labels':[{'field':'resource','value':resource}],
                 'unit':unit,'values':[{
                     'timestamp':datetime.datetime.fromtimestamp(
                         at,datetime.timezone.utc).isoformat(),
                     'value':value} for at,value in amounts]}]

    def samples(self, earlier=155_000_000, recent=165_000_000,
                limit=268_435_456):
        ages = (720,660,600,540,480,420,360,300,240,180,120,40)
        at = [self.NOW-age for age in ages]
        values = [(tick, earlier if i == 0 else recent)
                  for i,tick in enumerate(at)]
        return (self.series(values),
                self.series([(tick,limit) for tick in at]))

    def test_safe_never_grants_maintenance_without_other_proofs(self):
        usage,limits=self.samples()
        result=guard.assess(usage,limits,self.NOW)
        self.assertEqual(result['status'],'memory-headroom-observed')
        self.assertEqual(result['sampleCount'],12)
        self.assertFalse(result['maintenanceAuthorized'])
        self.assertIsNone(result['physicalBytesFreed'])

    def test_sparse_timeline_cannot_hide_an_intervening_spike(self):
        usage,limits=self.samples()
        # Two good measurements 11 minutes apart are never sufficient.
        usage[0]['values'] = [usage[0]['values'][0],usage[0]['values'][-1]]
        limits[0]['values'] = [limits[0]['values'][0],limits[0]['values'][-1]]
        self.assertEqual(guard.assess(usage,limits,self.NOW)['status'],
                         'memory-proof-unavailable')
        # A long gap fails even if there are eight or more good samples.
        usage,limits=self.samples()
        for series in (usage,limits):
            series[0]['values'] = series[0]['values'][:5] + series[0]['values'][9:]
        self.assertEqual(guard.assess(usage,limits,self.NOW)['status'],
                         'memory-proof-unavailable')

    def test_one_ram_spike_blocks_even_when_latest_is_low(self):
        usage,limits=self.samples(earlier=260_000_000,recent=100_000_000)
        result=guard.assess(usage,limits,self.NOW)
        self.assertEqual(result['status'],'memory-pressure')
        self.assertFalse(result['maintenanceAuthorized'])
        self.assertNotIn('private',str(result))

    def test_unknown_units_incomplete_recent_trends_stale_and_foreign_resource(self):
        valid,limits=self.samples()
        bad=[
            (self.series([(self.NOW-720,0.15),(self.NOW-40,0.18)],
                         unit='mystery'),limits),
            (self.series([(self.NOW-40,100_000_000)]),limits),
            (self.series([(self.NOW-1000,100_000_000),
                          (self.NOW-950,100_000_000)]),
             self.series([(self.NOW-1000,268_435_456),
                          (self.NOW-950,268_435_456)])),
            (self.series([(self.NOW-720,100_000_000),
                          (self.NOW-40,100_000_000)],resource='private-other'),
             limits),
            (valid,[]), (valid,[{'labels':[], 'values':123}]),
            ({'source':'untrusted'},limits),
        ]
        for usage,limit in bad:
            with self.subTest(case=repr(usage)[:80]):
                self.assertEqual(guard.assess(usage,limit,self.NOW)['status'],
                                 'memory-proof-unavailable')

    def test_unmatched_memory_spike_or_missing_usage_is_not_hidden(self):
        safe, limits = self.samples()
        # The first and last samples look safe; an extra unpaired high
        # usage reading between them must not disappear in an intersection.
        safe[0]['values'].insert(1, {
            'timestamp':datetime.datetime.fromtimestamp(
                self.NOW-400, datetime.timezone.utc).isoformat(),
            'value':265_000_000})
        self.assertEqual(guard.assess(safe,limits,self.NOW)['status'],
                         'memory-proof-unavailable')

        # Likewise an unpaired provider limit sample cannot be interpreted
        # as a complete 10-minute memory history.
        safe, limits = self.samples()
        limits[0]['values'].insert(1, {
            'timestamp':datetime.datetime.fromtimestamp(
                self.NOW-400, datetime.timezone.utc).isoformat(),
            'value':150_000_000})
        self.assertEqual(guard.assess(safe,limits,self.NOW)['status'],
                         'memory-proof-unavailable')

    def test_duplicate_memory_limit_uses_lower_bound(self):
        usage,limits=self.samples(recent=198_000_000)
        limits += self.series([(self.NOW-40,205_000_000)])
        self.assertEqual(guard.assess(usage,limits,self.NOW)['status'],
                         'memory-pressure')

    def test_boolean_nan_future_samples_cannot_be_safe(self):
        usage,limits=self.samples()
        for value in (True,float('nan'),-1):
            broken=self.series([(self.NOW-720,value),(self.NOW-40,80_000_000)])
            self.assertEqual(guard.assess(broken,limits,self.NOW)['status'],
                             'memory-proof-unavailable')
        future=self.series([(self.NOW+15,80_000_000),
                            (self.NOW+600,80_000_000)])
        self.assertEqual(guard.assess(future,limits,self.NOW)['status'],
                         'memory-proof-unavailable')

    def test_missing_api_key_has_no_network_calls(self):
        with patch.dict(os.environ,{},clear=True), \
             patch('urllib.request.build_opener') as network:
            result=guard.report()
        self.assertEqual(result['status'],'memory-proof-unavailable')
        network.assert_not_called()

    def test_clock_rollback_cannot_reuse_cached_headroom(self):
        cached = {'status':'memory-headroom-observed',
                  'newestSampleAt':self.NOW-40, 'maintenanceAuthorized':False}
        with patch.dict(os.environ,{'BOB_RENDER_METRICS_API_KEY':'synthetic'}), \
             patch.object(guard,'_cache',cached), \
             patch.object(guard,'_cached_at',self.NOW), \
             patch.object(guard.time,'time',return_value=self.NOW-600), \
             patch('urllib.request.build_opener',side_effect=OSError) as network:
            result = guard.report()
        self.assertEqual(result['status'],'memory-proof-unavailable')
        self.assertFalse(result['maintenanceAuthorized'])
        network.assert_called_once()

    def test_provider_errors_are_redacted_and_fail_closed(self):
        guard._cache=None
        with patch.dict(os.environ,{'BOB_RENDER_METRICS_API_KEY':'private-token'}), \
             patch('urllib.request.build_opener',
                   side_effect=RuntimeError('private-credential')):
            result=guard.report()
        self.assertEqual(result['status'],'memory-proof-unavailable')
        self.assertFalse(result['maintenanceAuthorized'])
        self.assertNotIn('private',repr(result))

    def test_bounded_two_read_only_requests_with_existing_token(self):
        usage,limits=self.samples()
        calls=[]
        class Response:
            def __init__(self, value):
                self.value=value
            def __enter__(self):
                return self
            def __exit__(self,*args):
                return False
            def read(self, amount):
                assert amount <= 1_000_001
                return json.dumps(self.value).encode()
        class Opener:
            def open(self, request,timeout):
                calls.append((request.full_url,timeout,request.get_method()))
                return Response(limits if '/memory-limit?' in request.full_url
                                else usage)
        guard._cache=None
        with patch.dict(os.environ,{'BOB_RENDER_METRICS_API_KEY':'private-token'}), \
             patch('urllib.request.build_opener',return_value=Opener()), \
             patch.object(guard.time,'time',return_value=self.NOW):
            result=guard.report()
            cached=guard.report()
        self.assertEqual(result['status'],'memory-headroom-observed')
        self.assertEqual(cached,result)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(method=='GET' and timeout==5 for _,timeout,method in calls))
        self.assertTrue(all(guard.RESOURCE in url for url,_,_ in calls))
        self.assertNotIn('private-token',repr(result))
        self.assertFalse(result['maintenanceAuthorized'])


if __name__=='__main__':
    unittest.main()
