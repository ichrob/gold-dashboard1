import copy
import json
import unittest
import bob_test_overview as overview
import paper_evidence_chain as chain
from test_paper_simulation import case,market,quote,NOW
import paper_simulation as sim
import paper_entry_review

class OverviewTests(unittest.TestCase):
    def test_handset_model_reaches_overview_without_becoming_strategy_performance(self):
        from test_handset_evidence_chain import sample
        from handset_evidence_chain import project
        data = {'areas': {'androidReader': {'evidenceChain': project([sample(),sample(3600)])}}}
        before = copy.deepcopy(data)
        view = overview.snapshot(data, NOW/1000)['handsetComparisons']
        self.assertEqual(view['accepted'], 1)
        self.assertEqual(view['missingFx'], 0)
        self.assertFalse(view['items'][0]['strategyPerformance'])
        self.assertAlmostEqual(view['items'][0]['modelNetEur'], -.01-2-(13.07+13.06)*.0005)
        self.assertNotIn('originalHash', json.dumps(view))
        self.assertEqual(data, before)
        cost = data['areas']['androidReader']['evidenceChain']['products'][0]['illustrativeReplay']['costModelReplay']
        cost['fxConversion'] = {'acceptedForModel': True, 'date':'2026-11-06', 'source':'ECB'}
        self.assertEqual(overview.snapshot(data,NOW/1000)['handsetComparisons']['dailyFxAccepted'],1)
        cost.update(status='missing-dated-fx',modelNetEur=None)
        view = overview.snapshot(data,NOW/1000)['handsetComparisons']
        self.assertEqual((view['accepted'],view['missingFx']),(0,1))
        self.assertEqual(overview.snapshot({},NOW/1000)['handsetComparisons']['status'],'unavailable')

    def test_absence_and_terminal_cases_are_not_success(self):
        r=overview.snapshot({'areas':{'comparisonHealth':{'items':{'three-stop-study':{'status':'observed','sampledRecords':4,'counts':{'terminal-not-necessarily-comparable':4}}}}}},NOW/1000)
        row=next(x for x in r['items'] if x['id']=='three-stop-study')
        self.assertFalse(row['completed']);self.assertIsNone(row['comparableCases'])
        self.assertIsNone(row['startedAt'])
        self.assertTrue(all(not x['completed'] for x in r['items']))
    def test_stale_account_cannot_claim_current_check(self):
        r=overview.snapshot({'areas':{'simulationAndPush':{'accounts':[{'profile':'a','checkedAt':NOW-121000,'recentCases':{'status':'unavailable'}}]}}},NOW/1000)
        row=r['items'][-1];self.assertEqual(row['state'],'unavailable');self.assertIsNone(row['sampledRecords'])
    def test_independent_comparison_evidence_restores_inventory_and_chains(self):
        evidence={'comparisonHealth':{'items':{'signals':{
            'status':'observed','sampledRecords':3,'counts':{'eligible':3}}}},
            'accountSamples':[{'profile':'balanced','recentCases':{'status':'observed',
                'items':[{'evidenceChain':{'complete':False}}]}}]}
        r=overview.snapshot({'areas':{'comparisonEvidence':evidence,
            'simulationAndPush':{'accounts':[]}}},NOW/1000)
        row=next(x for x in r['items'] if x['id']=='signals')
        self.assertEqual(row['state'],'observed')
        self.assertEqual(row['sampledRecords'],3)
        self.assertTrue(r['chainSampleAvailable'])
        self.assertEqual(len(r['evidenceChains']),1)
    def test_chain_preserves_history_and_rejects_later_settlement(self):
        c=case();before=copy.deepcopy(c)
        self.assertFalse(chain.review(c)['complete']);self.assertEqual(c,before)
        choice=c['product'];choice['direction']='LONG'
        c['selectionEvidence']=chain.capture_selection({'choices':[choice]},choice,NOW)
        c['entryChecklist']=paper_entry_review.capture(market(),choice,quote(),NOW,True,'test')
        c=sim.advance_case(c,{**market(),'price':89,'dataAt':NOW+30000},quote(NOW+30000),NOW+30000)
        self.assertTrue(chain.review(c)['complete'])
        c['status']='inconclusive'
        self.assertFalse(chain.review(c)['complete'])
        self.assertTrue(chain.review(c)['performanceExcluded'])
        self.assertFalse(chain.review(c)['brokerExecutionVerified'])
    def test_selection_capture_is_detached_and_allowlisted(self):
        selection={'choices':[{'isin':'test','score':3,'secret':'never'}]}
        result=chain.capture_selection(selection,{'isin':'test'},NOW)
        selection['choices'][0]['score']=9
        self.assertEqual(result['rankedShortlist'][0]['score'],3)
        self.assertNotIn('secret',json.dumps(result))
    def test_case_projection_keeps_safe_chain(self):
        import paper_case_review,bob_diagnostics
        c=case();c['secret']='never'
        safe=bob_diagnostics.project(paper_case_review.project_case(c),bob_diagnostics.CASE)
        self.assertIn('evidenceChain',safe);self.assertNotIn('never',json.dumps(safe))
