import copy
import unittest
import bob_operations as op

class OperationsTests(unittest.TestCase):
    def report(self):
        return {'observedAt':'2026-10-26T19:00:00Z','areas':{
            'products':{'status':'ok','lastCheckedAt':1000,'total':1,'incomplete':0,
                        'items':[{'isin':'TEST','fieldRecovery':{'state':'active'}}]},
            'problems':{'status':'ok','checkedAt':1000,'items':[
                {'code':'product-ko-validity-missing','number':1,'kiStatus':'waiting-for-evidence'},
                {'code':'product-ko-validity-missing','number':2,'kiStatus':'needs-user'}]},
            'background':{'status':'ok','lastSuccessAt':990},
            'collection':{'lastCycleAt':995,'updateIntervalSeconds':30}}}

    def test_complete_is_not_resolved_or_approved_and_duplicates_preserve_actions(self):
        r=self.report(); before=copy.deepcopy(r); v=op.snapshot(r,1000)
        self.assertEqual(r,before)
        self.assertEqual(v['productStatus']['state'],'complete')
        self.assertFalse(v['productStatus']['tradeApproved'])
        self.assertEqual(len(v['cases']),1)
        self.assertEqual(v['cases'][0]['issueNumbers'],[1,2])
        self.assertEqual(len(v['actions']),1)
        self.assertFalse(v['cases'][0]['repairVerified'])

    def test_conflict_takes_precedence_over_complete(self):
        r=self.report();r['areas']['products']['items'][0]['fieldRecovery']={'state':'conflict','conflicts':['ko','strike']}
        v=op.snapshot(r,1000)
        self.assertEqual(v['productStatus']['state'],'conflict')
        self.assertEqual(v['cases'][0]['comparison'],'source-conflict')

    def test_stale_future_missing_do_not_imply_success(self):
        for at in (None,1001,1):
            r=self.report();r['areas']['products']['lastCheckedAt']=at
            r['areas']['background']['lastSuccessAt']=at
            r['areas']['problems']['checkedAt']=None
            v=op.snapshot(r,1000)
            self.assertEqual(v['productStatus']['state'],'unknown')
            self.assertEqual(v['actionStatus'],'unknown')
            self.assertFalse(v['actions'])
            self.assertEqual(v['jobs'][0]['state'],'unknown')
            self.assertIsNone(v['jobs'][0]['expectedNextAt'])

    def test_collection_clock_is_not_success_and_sim_missing_unknown(self):
        v=op.snapshot(self.report(),1000)
        self.assertIsNone(v['jobs'][1]['lastSuccessAt'])
        self.assertEqual(v['jobs'][1]['lastObservedAt'],995)
        self.assertFalse(v['jobs'][1]['nextAttemptConfirmed'])
        self.assertEqual(v['jobs'][-1]['state'],'unavailable')
        self.assertFalse(v['historicalPolicy']['contributesToProfit'])

    def test_empty_list_and_incomplete_coverage_not_complete(self):
        for items,total in (([],0),([{}],2)):
            r=self.report();r['areas']['products'].update(items=items,total=total)
            self.assertNotEqual(op.snapshot(r,1000)['productStatus']['state'],'complete')

    def test_iso_requires_timezone(self):
        self.assertIsNone(op.stamp('2026-10-26T19:00:00'))
        self.assertEqual(op.stamp('2026-10-26T20:00:00+01:00'),op.stamp('2026-10-26T19:00:00Z'))

if __name__=='__main__': unittest.main()
