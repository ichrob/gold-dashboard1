"""No-trace, read-only handoff triage for Sunday's missing capture observations."""
import json
import unittest

from diagnostic_capture_handoff import STAGES, review
import bob_diagnostics as diag


def source(**changes):
    counts = dict.fromkeys(STAGES, 0)
    counts.update(input=20, analysis=20, push=20, health=20, transport=20)
    counts.update(changes)
    return dict(status='observed', counts=counts,
                totalSampled=sum(counts.values()), limitPerStage=20)


class CaptureHandoffTests(unittest.TestCase):
    def test_true_archived_stage_zero_means_only_no_capture_in_sample(self):
        result = review(source(), {'state':'paused','sessionMode':'weekend'})
        self.assertEqual(result['status'], 'observed-sample')
        self.assertEqual(result['push']['decisionStageSampled'], 20)
        self.assertEqual(result['push']['providerAttemptStageSampled'], 0)
        self.assertEqual(result['push']['handoffState'],
                         'push-decision-sampled-provider-stage-not-observed')
        self.assertEqual(result['paper']['inputStageSampled'], 0)
        self.assertEqual(result['paper']['sessionModeAtRead'], 'weekend')
        self.assertEqual(result['paper']['workerStateAtRead'], 'paused')
        self.assertIn('does NOT prove failed push', result['reviewReason'])
        for name in ('originalEventCorrelationVerified',
                     'androidDeliveryVerified', 'virtualExecutionVerified',
                     'continuousCaptureVerified'):
            self.assertFalse(result[name])
        self.assertFalse(result['realOrders'])

    def test_positive_two_stage_counts_are_never_trace_pairs_or_device_receipt(self):
        result = review(source(push=4, **{'push-delivery':3,'paper-input':5}),
                        {'state':'running','sessionMode':'trading'})
        self.assertEqual(result['push']['handoffState'],
             'push-and-provider-stages-separately-captured-not-paired')
        self.assertFalse(result['push']['tracePaired'])
        self.assertFalse(result['push']['deviceReceived'])
        self.assertEqual(result['paper']['handoffState'],
                         'paper-input-stage-observed-not-fill-proof')
        self.assertFalse(result['paper']['tradeOutcomeVerified'])

    def test_only_delivery_captured_does_not_make_up_decision(self):
        r=review(source(push=0, **{'push-delivery':1}))
        self.assertEqual(r['push']['handoffState'],
            'provider-attempt-sampled-decision-stage-not-observed')
        self.assertFalse(r['originalEventCorrelationVerified'])

    def test_missing_or_malformed_history_does_not_invent_zero_counts(self):
        for input_ in (None, [], {},
                       {'status':'insufficient'}, {'status':'observed'},
                       {'status':'observed','counts':{},'totalSampled':0,'limitPerStage':20}):
            with self.subTest(input_=str(input_)):
                got=review(input_)
                self.assertEqual(got['status'],'insufficient-evidence')
                self.assertNotIn('push', got)
                self.assertFalse(got['androidDeliveryVerified'])
        good=source()
        cases=(
            lambda x:x['counts'].update(health=True),
            lambda x:x['counts'].update(health=21),
            lambda x:x['counts'].update(health=-1),
            lambda x:x['counts'].update(health='SECRET'),
            lambda x:x['counts'].update(SECRET=1),
            lambda x:x['counts'].pop('input'),
            lambda x:x.update(totalSampled=3),
            lambda x:x.update(limitPerStage=2000),
            lambda x:x.update(status='all-verified'),
        )
        for change in cases:
            with self.subTest(case=str(change)):
                mutated=json.loads(json.dumps(good))
                change(mutated)
                r=review(mutated)
                self.assertEqual(r['status'],'insufficient-evidence')
                self.assertNotIn('push',r)
                self.assertNotIn('SECRET',json.dumps(r))

    def test_complete_empty_sample_does_not_prove_no_production_events(self):
        empty={**source(push=0,analysis=0,input=0,health=0,transport=0),
               'status':'warming'}
        r=review(empty)
        self.assertEqual(r['status'],'insufficient-evidence')
        self.assertEqual(r['push']['handoffState'],'neither-push-stage-observed')
        self.assertFalse(r['continuousCaptureVerified'])

    def test_private_report_projection_and_focus_survive_large_history(self):
        original=source(**{'push-delivery':0,'paper-input':0})
        raw={'account':'PRIVATE_ACCOUNT','token':'SECRET_KEY'}
        def fake_reader():
            return {
                'status':'observed',
                'paper':{'state':'paused','sessionMode':'weekend', **raw},
                'history':{'status':'observed',
                    'areas':{'journal':{'status':'observed',
                        'stageCoverage':{**original, 'secret':'NOT_FOR_VIEW'},
                        'events':[raw for _ in range(25)]}}},
            }
        full=diag.collect({'simulationAndPush':fake_reader})
        snapshot=full['areas']['diagnosticCaptureHandoff']
        self.assertEqual(snapshot['push']['decisionStageSampled'],20)
        self.assertFalse(snapshot['androidDeliveryVerified'])
        for focus in ('signals', 'repairs', 'simulation'):
            self.assertEqual(diag.focused_report(full,focus)['areas'][
                'diagnosticCaptureHandoff'],snapshot)
        self.assertNotIn('diagnosticCaptureHandoff',
                         diag.focused_report(full,'products')['areas'])
        compact=diag.bounded_report(full,5000)
        self.assertEqual(compact['areas']['diagnosticCaptureHandoff'],snapshot)
        snapshot_json=json.dumps(snapshot)
        for secret in ('PRIVATE_ACCOUNT','SECRET_KEY','NOT_FOR_VIEW'):
            self.assertNotIn(secret,snapshot_json)
        self.assertFalse(snapshot['paper']['tradeOutcomeVerified'])


if __name__=='__main__':
    unittest.main()
