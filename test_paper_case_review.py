import copy
import json
import os
import hashlib
import unittest
from unittest.mock import Mock, patch
import paper_case_review as r
import paper_simulation as sim
import paper_portfolios as profiles
import bob_diagnostics as diag

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(len(r.IDENTITIES),13)
        self.synthetic=[('balanced',1700000000000+i,1700000100000+i,1700000090000+i) for i in range(13)]
        self.manifest=patch.object(r,'IDENTITIES',{hashlib.sha256(json.dumps(key).encode()).hexdigest() for key in self.synthetic})
        self.manifest.start()
        self.addCleanup(self.manifest.stop)

    def case(self, identity=None):
        profile,start,end,last=identity or self.synthetic[0]
        return profile,dict(status='inconclusive',startedAt=start,closedAt=end,lastAt=last,
            productReturnKnown=True,productGrossPct=12.,netReturnKnown=False,
            events=[dict(kind='data-gap',recordedAt=end),dict(kind='deferred-sale',recordedAt=end+30000)])

    def test_exact_thirteen_separate_from_outcomes(self):
        keys=set()
        for identity in self.synthetic:
            profile,c=self.case(identity); old=copy.deepcopy(c)
            projected=r.project_case(c,profile)
            self.assertEqual(c,old)
            self.assertEqual(projected['status'],'inconclusive')
            self.assertEqual(projected['administrativeReview']['status'],r.STATUS)
            keys.add(projected['administrativeReview']['caseReviewId'])
            self.assertFalse(projected['performanceEligible'])
            self.assertIsNone(projected['productGrossPct'])
            self.assertEqual(projected['modelSettlementGrossPct'],12.)
        self.assertEqual(len(keys),13)

    def test_new_different_or_missing_evidence_does_not_close(self):
        profile,c=self.case()
        for patch in ({'startedAt':c['startedAt']+1},{'closedAt':c['closedAt']+1},
                      {'lastAt':None},{'lastAt':[]},{'status':'open'},{'events':[]}):
            self.assertIsNone(r.review({**c,**patch},profile))
        self.assertIsNone(r.review(c,'unknown'))

    def test_closed_review_not_repeated_in_attention_or_triage(self):
        profile,c=self.case(); projected=r.project_case(c,profile)
        areas={'simulationAndPush':{'status':'observed','accounts':[
            {'profile':profile,'recentCases':{'status':'observed','items':[projected]}}]}}
        self.assertFalse(any(x['state']=='inconclusive' for x in diag.summary(areas)['attention']))
        # A new unknown result remains a warning.
        areas['simulationAndPush']['accounts'][0]['recentCases']['items'].append({**c,'startedAt':c['startedAt']+1})
        self.assertTrue(any(x['state']=='inconclusive' for x in diag.summary(areas)['attention']))

    def test_correct_legacy_counts_without_touching_original(self):
        original=dict(inconclusive=2,productKnown=5,productPositive=3,productNegative=2)
        adjusted=r.adjust_daily(original,(2,1,1))
        self.assertEqual(original['productKnown'],5)
        self.assertEqual(adjusted['productKnown'],3)
        metric=profiles.performance_snapshot({'daily':[adjusted]})
        self.assertEqual(metric['performanceExcluded'],2)
        self.assertAlmostEqual(metric['productPositiveRatePct'],66.67)
        invalid=r.adjust_daily(original,(9,5,4))
        self.assertIsNone(profiles.performance_snapshot({'daily':[invalid]})['productPositiveRatePct'])

    def test_future_deferred_sale_does_not_count_as_product_success(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=None
        c=dict(status='inconclusive',productReturnKnown=True,productGrossPct=20.,goldR=0.)
        sim.day_update(conn,'2026-10-26',closed=c)
        payload=json.loads(conn.execute.call_args.args[1][1])
        self.assertEqual(payload['inconclusive'],1)
        self.assertEqual(payload['productKnown'],0)
        self.assertEqual(c['performanceAccountingVersion'],2)

    def test_gap_event_retains_actual_worker_input_without_backdating(self):
        from test_paper_portfolios import market, quote, NOW, ISIN
        original=sim.new_case(market(),{'isin':ISIN},quote(),NOW)
        observed={**market(),'priceFresh':False,'dataAt':NOW,'analysisBarAt':NOW-900000}
        case=sim.advance_case(original,observed,None,NOW+120000)
        event=next(e for e in case['events'] if e['kind']=='data-gap')
        self.assertEqual(event['inputEvidence']['dataAt'],NOW)
        self.assertFalse(event['inputEvidence']['priceFresh'])
        self.assertEqual(event['recordedAt'],NOW+120000)
        self.assertEqual(event['inputEvidence']['analysisBarAt'],NOW-900000)
        self.assertNotIn('inputEvidence',original['events'][0])

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL required')
    def test_legacy_sql_excludes_only_pre_fix_counted_results(self):
        import psycopg
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute('CREATE TEMP TABLE bob_paper_cases(day TEXT,payload JSONB)')
            for payload in (dict(status='inconclusive',productCounted=True,productGrossPct=12),
                            dict(status='inconclusive',productCounted=True,productGrossPct=-1),
                            dict(status='inconclusive',productCounted=True,productGrossPct=6,performanceAccountingVersion=2),
                            dict(status='closed',productCounted=True,productGrossPct=7)):
                conn.execute('INSERT INTO bob_paper_cases VALUES(%s,%s::jsonb)',('2026-10-26',json.dumps(payload)))
            self.assertEqual(r.legacy_exclusions(conn),{'2026-10-26':(2,1,1)})

if __name__=='__main__': unittest.main()
