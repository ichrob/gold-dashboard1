import copy
import json
import unittest
import bob_test_overview as overview
import paper_evidence_chain as chain
from test_paper_simulation import case,market,quote,NOW
import paper_simulation as sim
import paper_entry_review

class OverviewTests(unittest.TestCase):
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
