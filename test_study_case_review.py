import copy
import unittest
import study_case_review as r


def case():
    at=r.CUTOFF-7200000
    return dict(id='synthetic', status='inconclusive', study='entry-delay',
        at=at,endAt=at+3600000,closedAt=at+3601000,costAssumptionPct=.16,
        exit=dict(at=at+3600000,price=102),dataGap=True,
        legs={'0s':dict(direction='LONG',entry=dict(at=at,price=100)),
              'wait':dict(wait=True,entry=None)})


class HistoricalReviewTests(unittest.TestCase):
    def test_model_is_separate_and_does_not_rewrite_original(self):
        c=case();before=copy.deepcopy(c);out=r.review(c)
        self.assertEqual(c,before)
        self.assertEqual(out['modelStatus'],'endpoint-model')
        self.assertAlmostEqual(out['returnsPct']['0s'],1.84)
        self.assertEqual(out['returnsPct']['wait'],0)
        self.assertFalse(out['originalResultVerified'])
        self.assertFalse(out['performanceEligible'])
        self.assertFalse(out['pathComplete'])
        self.assertEqual(out['koOutcome'],'unknown')
        c['legs']['0s']['direction']='SHORT'
        self.assertAlmostEqual(r.review(c)['returnsPct']['0s'],-2.16)

    def test_missing_or_invalid_points_close_without_inventing_returns(self):
        for update in ({'exit':None},{'costAssumptionPct':float('nan')},
                       {'legs':{'missing':{'entry':None}}},
                       {'exit':{'at':r.CUTOFF,'price':102}},
                       {'exit':{'at':case()['endAt'],'price':-1}},
                       {'exit':{'at':case()['endAt'],'price':102,'estimated':True}}):
            c=case();c.update(update);out=r.review(c)
            self.assertEqual(out['status'],'closed-original-unresolved')
            self.assertEqual(out['modelStatus'],'unavailable')
            self.assertEqual(out['returnsPct'],{})

    def test_new_pending_complete_and_companion_cases_are_not_closed(self):
        for change in ({'closedAt':r.CUTOFF+1},{'status':'pending'},
                       {'status':'complete'},{'simulationOnly':True},
                       {'id':'synthetic:model-v1'},{'closedAt':float('nan')}):
            c=case();c.update(change);self.assertIsNone(r.review(c))

    def test_report_is_bounded_and_counts_only_reviewed_originals(self):
        class Conn:
            def execute(self,sql,args):
                self.args=args;self.sql=sql;return self
            def fetchall(self):
                return [(case(),),(dict(case(),exit=None),),(dict(case(),simulationOnly=True),)]
        conn=Conn();out=r.report(conn,'synthetic-campaign')
        self.assertEqual(out['counts'],dict(reviewed=2,modeled=1,unavailable=1))
        self.assertIn('LIMIT',conn.sql)
        self.assertFalse(out['truncated'])
