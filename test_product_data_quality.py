import unittest
from product_data_quality import snapshot,summarize,stamp

class QualityTests(unittest.TestCase):
    def test_snapshot_identity_and_copy(self):
        q=dict(isin='A',currency='EUR',bid=2,bidAt='2026-10-18T10:00:00Z',metadata={'ko':3},eligible=False)
        a=snapshot(q);b=snapshot(q)
        self.assertEqual(a['snapshotId'],b['snapshotId'])
        self.assertNotEqual(a['snapshotId'],snapshot(dict(q,currency='CHF'))['snapshotId'])
        self.assertNotEqual(a['snapshotId'],snapshot(dict(q,bidAt='2026-10-18T10:01:00Z'))['snapshotId'])
        a['metadata']['ko']=9
        self.assertEqual(q['metadata']['ko'],3)
        self.assertFalse(a['eligible'])

    def test_unknown_is_not_zero_or_complete(self):
        for report in ({},{'status':'ok','lastCheckedAt':'2026-10-18T10:00:00Z','items':[]}):
            r=summarize(report,stamp('2026-10-18T10:01:00Z'))
            self.assertIsNone(r['freshPct']);self.assertIsNone(r['completePct'])

    def test_current_stale_and_separate_currency_comparisons(self):
        at='2026-10-18T10:00:00Z'
        report=dict(status='ok',lastCheckedAt=at,items=[dict(isin='A',state='issuer-evidence-complete',missing=[],quoteSourceAt=at),dict(isin='B',state='incomplete',missing=['quote'],missingSince={'quote':at},marketCrossCheck={'status':'outlier'})],priceStudy={'A':dict(rawMae=.1,validationCount=5,currency='EUR'),'B':dict(rawMae=.2,validationCount=7,currency='CHF')})
        report['items'][0]['quoteSourceAt']=stamp(at)
        r=summarize(report,stamp(at)+60000)
        self.assertEqual((r['freshPct'],r['completePct']),(50,50))
        self.assertEqual(r['conflicts'],['B']);self.assertEqual(r['gaps'][0]['minutes'],1)
        self.assertEqual([x['currency'] for x in r['comparisons']],['EUR','CHF'])
        r=summarize(report,stamp(at)+180001)
        self.assertEqual(r['status'],'stale');self.assertIsNone(r['freshPct'])
