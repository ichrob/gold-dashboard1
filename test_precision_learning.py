import copy
import unittest
import precision_learning as p

START=1800000000000


def step(state,i,bias=.01):return p.transition(state,dict(at=START+i*60000,quoted=10*(1+bias),estimated=10))


class LearningTests(unittest.TestCase):
    def trained(self):
        s=p.initial()
        for i in range(30):s=step(s,i)
        return s
    def test_frozen_holdout_and_later_reversal(self):
        s=self.trained();self.assertEqual(s['phase'],'validation')
        self.assertEqual(s['rows'],[]);self.assertEqual(s['factor'],0)
        for i in range(30,90):s=step(s,i)
        self.assertTrue(p.policy(s,START+89*60000)['usable'])
        self.assertAlmostEqual(s['factor'],.01)
        self.assertEqual(s['evidence']['count'],60)
        for i in range(90,110):s=step(s,i,-.01)
        self.assertEqual(s['phase'],'cooldown');self.assertEqual(s['factor'],0)
        self.assertEqual(s['events'][-1]['event'],'rollback')
    def test_opposite_holdout_never_adopted_or_refit(self):
        s=self.trained();candidate=s['candidate']
        for i in range(30,90):s=step(s,i,-.01)
        self.assertEqual(s['candidate'],candidate);self.assertEqual(s['phase'],'cooldown')
        self.assertFalse(p.policy(s,START+89*60000)['usable'])
    def test_stale_lease_gap_duplicate_and_bounds(self):
        s=p.initial()
        for i in range(90):s=step(s,i)
        self.assertFalse(p.policy(s,START+92*60000)['usable'])
        unchanged=copy.deepcopy(s);self.assertEqual(step(s,89,-.1),unchanged)
        s=step(s,94);self.assertEqual(s['phase'],'training');self.assertEqual(s['factor'],0)
        s=p.initial()
        for i in range(30):s=step(s,i,.04)
        self.assertEqual(s['phase'],'cooldown')
    def test_identity_isolates_terms_source_currency_and_scope(self):
        product=dict(isin='DE000TEST000',currency='EUR',direction='LONG',ratio=.1,strike=4000,ko=4000)
        base=p.identity(product,'one')
        for changed in (dict(currency='CHF'),dict(ko=3999),dict(_precisionScope='trade-1'),dict(ratio=.01)):
            self.assertNotEqual(base,p.identity(dict(product,**changed),'one'))
        self.assertNotEqual(base,p.identity(product,'two'))
    def test_no_claim_from_too_few_independent_blocks(self):
        rows=[dict(at=START+i*100,quoted=10.1,estimated=10) for i in range(100)]
        self.assertIsNone(p.lower_bound(rows,.01))
