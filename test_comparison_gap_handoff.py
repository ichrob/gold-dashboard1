import copy
import unittest
import types
from contextlib import nullcontext
from unittest.mock import Mock, patch
import bob_diagnostics as d

class GapHandoffTests(unittest.TestCase):
    def test_probes_isolate_failure_and_keep_other_original_observations(self):
        conn=Mock();conn.transaction.side_effect=lambda:nullcontext()
        samples=[{'profile':'sample','recentCases':{'status':'observed','items':[]}}]
        modules={name:types.SimpleNamespace(report=Mock(return_value={'status':'observed','readOnly':True}))
                 for name in ('paper_gap_archive','paper_gap_analysis_archive','paper_input_evidence')}
        modules['paper_gap_analysis_archive'].report.side_effect=RuntimeError('private detail')
        modules['paper_input_evidence'].latest=Mock(return_value={'status':'observed','observedAt':12345})
        with patch.dict('sys.modules',modules):out=d.comparison_gap_evidence(conn,samples)
        self.assertEqual(out['spotGapArchive']['status'],'observed')
        self.assertEqual(out['analysisGapArchive']['status'],'unavailable')
        self.assertEqual(out['paperInputLatest']['observedAt'],12345)
        self.assertNotIn('private detail',str(out))
        modules['paper_gap_archive'].report.assert_called_once_with(conn,samples)
        self.assertTrue(all(c.args[0].startswith('SET LOCAL') for c in conn.execute.call_args_list))

    def test_split_report_restores_archive_projection_without_mutating_live_state(self):
        live={'status':'observed','accounts':[{'profile':'sample','status':'running',
              'recentCases':{'status':'observed','items':[]}}]}
        before=copy.deepcopy(live)
        comparison={'gapEvidence':{'spotGapArchive':{'status':'observed','readOnly':True,
                    'items':[{'eventAt':1000,'nearestSourceAt':990,'state':'nearby-original-observed'}]},
                    'paperInputLatest':{'status':'observed','observedAt':2000,'private':'hidden'}}}
        result=d.simulation_evidence_snapshot(live,comparison)
        self.assertEqual(result['spotGapArchive']['items'][0]['nearestSourceAt'],990)
        self.assertEqual(result['paperInputLatest']['observedAt'],2000)
        self.assertNotIn('private',result['paperInputLatest'])
        self.assertEqual(live,before)

if __name__=='__main__':unittest.main()
