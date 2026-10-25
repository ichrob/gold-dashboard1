"""Read-only aggregate counts survive Bob diagnostic response truncation."""
import json
import unittest
from copy import deepcopy

import bob_diagnostics as diag


STAGES=('input', 'analysis', 'analysis-failed', 'push', 'push-delivery',
        'paper-input', 'health', 'transport')


def collected(summary):
    return diag.collect({'simulationAndPush':lambda:{
        'status':'observed',
        'history':{'status':'observed', 'areas':{'journal':{
            'status':'observed', 'stageCoverage':summary,
            'events':[{'token':'PRIVATE-RAW-DIAGNOSTIC'}],
        }}}
    }})


class StageCountTests(unittest.TestCase):
    def test_only_eight_fixed_stage_counts_and_no_raw_fields(self):
        counts=dict.fromkeys(STAGES,0)
        counts['push-delivery']=3
        counts['paper-input']=5
        evidence={'status':'observed', 'counts':counts,
                  'totalSampled':8,'limitPerStage':20,
                  'secret':'NEVER-PUBLISH','handsetDeliveryVerified':True}
        report=collected(evidence)
        sample=report['areas']['diagnosticStageCoverage']
        self.assertEqual(sample['status'],'observed')
        self.assertEqual(sample['totalSampled'],8)
        self.assertEqual(sample['counts']['push-delivery'],3)
        self.assertEqual(sample['counts']['paper-input'],5)
        self.assertFalse(sample['handsetDeliveryVerified'])
        self.assertFalse(sample['paperExecutionVerified'])
        self.assertFalse(sample['realOrders'])
        for private in ('NEVER-PUBLISH','PRIVATE-RAW-DIAGNOSTIC','secret','token'):
            self.assertNotIn(private,json.dumps(sample))
        for focus in ('simulation','signals','repairs'):
            self.assertEqual(diag.focused_report(report,focus)['areas'][
                'diagnosticStageCoverage'],sample)
        self.assertNotIn('diagnosticStageCoverage',
                         diag.focused_report(report,'products')['areas'])

    def test_invalid_counts_fail_closed_no_fake_zero_or_success(self):
        counts=dict.fromkeys(STAGES,0)
        valid={'status':'observed','counts':counts,
               'totalSampled':0,'limitPerStage':20}
        cases=(
            lambda x:x.update(totalSampled=1),
            lambda x:x.update(limitPerStage=2000),
            lambda x:x['counts'].update(health=21),
            lambda x:x['counts'].update(health=-1),
            lambda x:x['counts'].update(health=True),
            lambda x:x['counts'].update(health='secret-token'),
            lambda x:x['counts'].update(privateEndpoint=1),
            lambda x:x['counts'].pop('paper-input'),
            lambda x:x.update(status='verified-device'),
        )
        for action in cases:
            with self.subTest(case=str(action)):
                fake=deepcopy(valid)
                action(fake)
                area=collected(fake)['areas']['diagnosticStageCoverage']
                self.assertEqual(area['status'],'insufficient')
                self.assertNotIn('counts',area)
                self.assertFalse(area['handsetDeliveryVerified'])
                self.assertFalse(area['paperExecutionVerified'])

    def test_partial_historical_journal_does_not_claim_complete_handoffs(self):
        counts=dict.fromkeys(STAGES,0)
        counts['push']=1
        fake={'status':'warming','counts':counts,'totalSampled':1,
              'limitPerStage':20}
        report=collected(fake)
        sample=report['areas']['diagnosticStageCoverage']
        self.assertEqual(sample['status'],'warming')
        self.assertFalse(sample['handsetDeliveryVerified'])
        self.assertEqual(sample['counts']['paper-input'],0)
        self.assertNotIn('continuousCoverageVerified',sample)


if __name__=='__main__':
    unittest.main()
