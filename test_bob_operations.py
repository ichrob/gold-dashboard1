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

    def test_unconfirmed_terms_survive_projection_and_prevent_complete_label(self):
        import bob_diagnostics as diagnostics
        r=self.report()
        item=r['areas']['products']['items'][0]
        item['timeEvidence']={'terms':{'ko':{'conditionVerified':False,
            'validityUnconfirmed':True,'reviewedAt':999,'secret':'PRIVATE'},
            'strike':{'conditionVerified':True}}}
        item['leverageObservation']={'value':10,'kind':'shared-issuer-observation',
                                    'researchOnly':True}
        r['areas']['products']=diagnostics.product_snapshot(r['areas']['products'])
        v=op.snapshot(r,1000)
        self.assertEqual(v['productStatus']['state'],'incomplete')
        self.assertEqual(v['productStatus']['unconfirmedTermsCount'],1)
        self.assertEqual(v['cases'][0]['comparison'],'current-product-evidence-not-complete')
        self.assertFalse(v['productStatus']['tradeApproved'])
        self.assertNotIn('PRIVATE',str(r))
        projected=r['areas']['products']['items'][0]
        self.assertTrue(projected['leverageObservation']['researchOnly'])
        self.assertEqual(projected['timeEvidence']['terms']['ko']['reviewedAt'],999)
        report=diagnostics.summary(r['areas'])
        self.assertTrue(any(x.get('meaning')=='original-term-validity-unconfirmed'
                            for x in report['attention']))

    def test_verified_terms_do_not_create_gap(self):
        r=self.report()
        r['areas']['products']['items'][0]['timeEvidence']={'terms':{
            'ko':{'conditionVerified':True,'validityUnconfirmed':False}}}
        self.assertEqual(op.snapshot(r,1000)['productStatus']['state'],'complete')

    def test_source_decision_is_visible_without_hiding_raw_conflict(self):
        r=self.report()
        r['areas']['products']['items'][0]['fieldRecovery']={
            'state':'conflict','conflicts':['strike'],
            'sourceDecisions':{'strike':{'state':'dated-issuer-selected','primaryValue':4200,'referenceValue':4199}}}
        v=op.snapshot(r,1000)
        self.assertEqual(v['productStatus']['state'],'differences-explained')
        self.assertEqual(v['productStatus']['unresolvedCount'],0)
        conflict=v['productStatus']['conflicts'][0]
        self.assertIn('Emittentenangabe gewählt',conflict['resolution'])
        self.assertEqual(conflict['sourceDecisions']['strike']['referenceValue'],4199)
        self.assertFalse(v['productStatus']['tradeApproved'])

    def test_source_decisions_survive_actual_diagnostic_projection(self):
        import bob_diagnostics as diagnostics
        r=self.report()
        recovery={'state':'conflict','checkedAt':999,'conflicts':['strike'],
            'unresolvedConflicts':[],
            'sourceDecisions':{'strike':{'state':'dated-issuer-selected',
                'reason':'Dated issuer selected', 'source':'https://issuer.example/item?token=PRIVATE',
                'dateText':'27.10.2026','sourceTimeRaw':'2026-10-27T01:35:45',
                'primaryValue':4200,'referenceValue':4199,'token':'PRIVATE'},
                'unexpected':{'secret':'PRIVATE'}}}
        r['areas']['products']['items'][0].update(fieldRecovery=recovery,tradeApproved=False)
        before=copy.deepcopy(r)
        r['areas']['products']=diagnostics.product_snapshot(r['areas']['products'])
        v=op.snapshot(r,1000)
        conflict=v['productStatus']['conflicts'][0]
        self.assertIn('Emittentenangabe gewählt',conflict['resolution'])
        decision=conflict['sourceDecisions']['strike']
        self.assertEqual(decision['dateText'],'27.10.2026')
        self.assertEqual(decision['sourceTimeRaw'],'2026-10-27T01:35:45')
        self.assertEqual(decision['primaryValue'],4200)
        self.assertEqual(decision['referenceValue'],4199)
        self.assertEqual(decision['reason'],'Dated issuer selected')
        self.assertNotIn('PRIVATE',str(v))
        self.assertNotIn('unexpected',str(v))
        self.assertEqual(conflict['fields'],['strike'])
        self.assertFalse(v['productStatus']['tradeApproved'])
        self.assertEqual(recovery,before['areas']['products']['items'][0]['fieldRecovery'])

    def test_partial_missing_or_malformed_decision_stays_unresolved(self):
        import bob_diagnostics as diagnostics
        for decisions in ({}, None, [], {'ko':None},
                {'ko':{'state':'dated-issuer-selected'}},
                {'ko':{'state':'dated-issuer-selected'},'strike':{'state':'unresolved'}}):
            with self.subTest(decisions=decisions):
                r=self.report()
                r['areas']['products']['items'][0]['fieldRecovery']={
                    'state':'conflict','conflicts':['ko','strike'],
                    'unresolvedConflicts':['strike'],'sourceDecisions':decisions}
                r['areas']['products']=diagnostics.product_snapshot(r['areas']['products'])
                self.assertEqual(r['areas']['products']['items'][0]
                    ['fieldRecovery']['unresolvedConflicts'],['strike'])
                v=op.snapshot(r,1000)
                self.assertEqual(v['productStatus']['state'],'conflict')
                self.assertIn('noch nicht bestätigt',v['productStatus']['conflicts'][0]['resolution'])
                self.assertFalse(v['productStatus']['tradeApproved'])

    def test_explicit_unresolved_field_wins_over_selected_decision(self):
        r=self.report()
        r['areas']['products']['items'][0]['fieldRecovery']={
            'state':'conflict','conflicts':['ko'],'unresolvedConflicts':['ko'],
            'sourceDecisions':{'ko':{'state':'dated-issuer-selected'}}}
        out=op.snapshot(r,1000)
        self.assertEqual(out['productStatus']['state'],'conflict')
        self.assertEqual(out['productStatus']['unresolvedCount'],1)

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

