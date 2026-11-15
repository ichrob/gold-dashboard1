"""No simulation status should disappear just because its history is large.

Synthetic only; no DB access, market assumptions, broker orders or trade-state
mutations.
"""
import copy
import json
import unittest

import bob_diagnostics as d


class SimulationRuntimeBriefTests(unittest.TestCase):
    def sample(self):
        return {
            'status':'observed',
            'paper':{'state':'degraded','sessionMode':'trading',
                     'accountsTotal':9,'accountsChecked':7,
                     'maxCheckAgeSeconds':512,'secret':'NOT_FOR_REPORT'},
            'accounts':[{'profile':'trend800nov','status':'running',
                         'checkedAt':1794214500000,'private':'NOT_FOR_REPORT'},
                        {'profile':'normal1000nov','status':'running'},
                        {'profile':'trend800','status':'completed'}],
            'push':{'evaluator':{'completed':320,'failed':1,
                                'queueTimeouts':2},'private':'NOT_FOR_REPORT'},
            'qualityCampaign':{'status':'observed','originalCases':['SECRET']},
            'reportAdmission':{'activeLoads':1,'capacityTimeouts':2},
            'history':{'data':'x'*35000},
        }

    def test_brief_preserves_degraded_state_without_private_data(self):
        sample=self.sample()
        copy_before=copy.deepcopy(sample)
        brief=d.simulation_runtime_brief(sample)
        self.assertEqual(sample,copy_before)
        self.assertEqual(brief['status'],'partial')
        self.assertEqual(brief['paper']['state'],'degraded')
        self.assertEqual(brief['paper']['accountsChecked'],7)
        self.assertEqual(brief['runningProfiles'],2)
        self.assertEqual(brief['completedProfiles'],1)
        self.assertEqual(brief['evaluator']['queueTimeouts'],2)
        self.assertFalse(brief['freshMarketInputsVerified'])
        self.assertFalse(brief['strategyWinnerConfirmed'])
        self.assertNotIn('NOT_FOR_REPORT',str(brief))
        self.assertNotIn('SECRET',str(brief))
        self.assertLess(len(json.dumps(brief).encode()),1500)

    def test_missing_heartbeat_fails_closed(self):
        brief=d.simulation_runtime_brief({'status':'observed','accounts':[]})
        self.assertEqual(brief['status'],'unavailable')
        self.assertTrue(brief['readOnly'])
        self.assertFalse(brief['realOrders'])

    def test_large_simulation_omission_keeps_independent_heartbeat(self):
        sim=self.sample()
        source={'areas':{
            'simulationAndPush':sim,
            'simulationRuntimeBrief':d.simulation_runtime_brief(sim),
            'paperProfitEvidence':{'status':'observed'}}}
        before=copy.deepcopy(source)
        bounded=d.bounded_report(source, 2200)
        self.assertEqual(source,before)
        self.assertEqual(bounded['areas']['simulationRuntimeBrief']['paper']['state'],'degraded')
        self.assertEqual(bounded['areas']['simulationRuntimeBrief']['status'],'partial')
        self.assertLess(len(json.dumps(bounded).encode()),2200)
        self.assertNotIn('x'*100,json.dumps(bounded))


if __name__ == '__main__':
    unittest.main()
