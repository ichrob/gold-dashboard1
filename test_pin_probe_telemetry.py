import unittest
from datetime import datetime, timezone, timedelta
from android_telemetry import validate_report, PIN_RESULTS, BOOLS

class PinTelemetry(unittest.TestCase):
    def test_local_login_only_accepts_fixed_result_without_credentials_or_success_claim(self):
        report=self.report()
        report['pinProbe']={**self.probe(), 'result':'LOCAL_PIN_ENTRY_SENT'}
        self.assertEqual(validate_report(report)['pinProbe']['result'], 'LOCAL_PIN_ENTRY_SENT')
        for extra in ({'pin':'synthetic'}, {'digits':[0,1,2,3,4]}, {'account':'synthetic'},
                      {'exerciseTrace':{'stage':'DELETE_ACCEPTED','reason':'STATE_CYCLE'}},
                      {'result':'LOCAL_PIN_LOGIN_SUCCESS'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_report(dict(report, pinProbe=report['pinProbe'] | extra))

    def test_dialog_outcomes_contain_no_screen_text_or_credentials(self):
        for result in ('LOCAL_PIN_HOME_VISIBLE', 'LOCAL_PIN_DIALOG_UNCHANGED',
                       'LOCAL_PIN_DIALOG_UNRECOGNIZED', 'LOCAL_PIN_DIALOG_BLOCKED',
                       'LOCAL_PIN_DIALOG_REPEATED', 'LOCAL_PIN_DIALOG_ACTION_FAILED'):
            report = dict(self.report(), pinProbe=dict(self.probe(), result=result))
            self.assertEqual(validate_report(report)['pinProbe']['result'], result)
            for extra in ({'dialogText':'synthetic'}, {'pin':'synthetic'}, {'bounds':[1,2,3,4]}):
                with self.assertRaises(ValueError):
                    validate_report(dict(report, pinProbe=report['pinProbe'] | extra))

    def test_cancelled_delete_touch_never_reports_a_cycle_or_an_earlier_stage(self):
        from android_telemetry import validate_pin_exercise_trace
        trace={'stage':'DELETE_ACCEPTED','reason':'DELETE_TOUCH_CANCELLED'}
        validate_pin_exercise_trace(trace, 'KEYPAD_TEST_INTERRUPTED')
        for result, stage in [('KEYPAD_TEST_STATE_CYCLE_OBSERVED','DELETE_ACCEPTED'),
                              ('KEYPAD_TEST_INTERRUPTED','DIGIT_ACCEPTED'),
                              ('KEYPAD_TEST_INTERRUPTED','DELETE_REQUESTED')]:
            with self.subTest(result=result, stage=stage), self.assertRaises(ValueError):
                validate_pin_exercise_trace(dict(trace, stage=stage), result)

    def test_cancelled_touch_cannot_claim_delete_or_state_cycle(self):
        from android_telemetry import validate_pin_exercise_trace
        trace={'stage':'DIGIT_ACCEPTED','reason':'DIGIT_TOUCH_CANCELLED'}
        validate_pin_exercise_trace(trace, 'KEYPAD_TEST_INTERRUPTED')
        for result, stage in [('KEYPAD_TEST_STATE_CYCLE_OBSERVED','DIGIT_ACCEPTED'),
                              ('KEYPAD_TEST_INTERRUPTED','DELETE_ACCEPTED'),
                              ('KEYPAD_TEST_INTERRUPTED','WAITING')]:
            with self.subTest(result=result, stage=stage), self.assertRaises(ValueError):
                validate_pin_exercise_trace(dict(trace, stage=stage), result)

    def test_interruption_preserves_progress_and_fixed_reason(self):
        from android_telemetry import PIN_EXERCISE_STAGES
        for stage in PIN_EXERCISE_STAGES:
            report=self.report()
            report['pinProbe']={**self.probe(), 'result':'KEYPAD_TEST_INTERRUPTED',
                'exerciseTrace':{'stage':stage, 'reason':'TARGET_REFRESH_FAILED'}}
            self.assertEqual(validate_report(report)['pinProbe']['exerciseTrace']['stage'], stage)
    def test_trace_rejects_free_text_and_false_action_success(self):
        bad=[{'stage':'secret', 'reason':'STOPPED'}, {'stage':'WAITING', 'reason':[]},
             {'stage':0, 'reason':'STOPPED'}, {'stage':'WAITING', 'reason':'text from screen'},
             {'stage':'WAITING', 'reason':'STOPPED', 'pin':'12345'}]
        for trace in bad:
            report=self.report()
            report['pinProbe']={**self.probe(), 'result':'KEYPAD_TEST_INTERRUPTED', 'exerciseTrace':trace}
            with self.subTest(trace=trace), self.assertRaises(ValueError): validate_report(report)
        for result in ('NO_INPUT', 'KEYPAD_TEST_STATE_CYCLE_OBSERVED', 'KEYPAD_TEST_DIGIT_REJECTED'):
            report=self.report()
            report['pinProbe']={**self.probe(), 'result':result,
                'exerciseTrace':{'stage':'WAITING','reason':'STOPPED'}}
            with self.subTest(result=result), self.assertRaises(ValueError): validate_report(report)
    def test_trace_enum_contract_matches_android(self):
        import re
        from pathlib import Path
        from android_telemetry import PIN_EXERCISE_STAGES, PIN_EXERCISE_REASONS
        source=(Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion/PinKeypadExerciseTrace.kt').read_text()
        for name, expected in [('Stage', PIN_EXERCISE_STAGES), ('Reason', PIN_EXERCISE_REASONS)]:
            block=re.search(r'enum class '+name+r'\s*\{([^}]+)', source).group(1)
            self.assertEqual(set(re.findall(r'\b[A-Z_]+\b', block)), set(expected))
    def flags(self, **changes):
        return dict(enabled=False, labelled=False, clickableFlag=True,
                    clickAction=True, nearbyParentAction=False) | changes
    def test_symbol_flags_roundtrip_and_disabled_keeps_parent_information(self):
        report=self.report()
        report['pinProbe']={**self.probe(), 'result':'SYMBOL_DISABLED',
                            'symbolFlags':self.flags(nearbyParentAction=True)}
        self.assertEqual(validate_report(report)['pinProbe'], report['pinProbe'])
    def test_symbol_flags_reject_content_extra_keys_types_and_mismatched_result(self):
        cases=[self.flags(pin='12345'), self.flags(labelled='secret'),
               self.flags(enabled=0), self.flags(clickAction=None),
               self.flags(bounds=[1,2,3,4]), {}, [], 'text',
               self.flags(enabled=True)]
        for flags in cases:
            report=self.report()
            report['pinProbe']={**self.probe(), 'result':'SYMBOL_DISABLED', 'symbolFlags':flags}
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                validate_report(report)
        for result in ('SENSITIVE_INPUT', 'INCOMPLETE', 'SYMBOL_NODES_MULTIPLE', 'LOGIN_DELETE_OFFERED'):
            report=self.report()
            report['pinProbe']={**self.probe(), 'result':result, 'symbolFlags':self.flags()}
            with self.subTest(result=result), self.assertRaises(ValueError):
                validate_report(report)
    def report(self):
        return dict(reportId='a'*32, observedAt=datetime.now(timezone.utc).isoformat(),
            appVersionCode=10315, lastCode='NONE', lastEventAt=None, **{k:False for k in BOOLS})
    def probe(self):
        return dict(runId='b'*32, endedAt=datetime.now(timezone.utc).isoformat(),
                    result='NO_WINDOW', completed=True)
    def test_legacy_reports_remain_valid(self):
        self.assertNotIn('pinProbe', validate_report(self.report()))
    def test_all_fixed_results_roundtrip_without_touching_product_code(self):
        for code in PIN_RESULTS:
            report=self.report(); report['pinProbe']={**self.probe(), 'result':code}
            self.assertEqual(validate_report(report)['pinProbe']['result'], code)
            self.assertEqual(validate_report(report)['lastCode'], 'NONE')
    def test_rejects_credentials_free_text_bad_types_and_stale_results(self):
        cases=[{**self.probe(), 'pin':'12345'}, {**self.probe(), 'screenText':'example'},
               {**self.probe(), 'result':'12345'}, {**self.probe(), 'completed':1},
               {**self.probe(), 'runId':'user'}, {**self.probe(), 'result':[]},
               {**self.probe(), 'endedAt':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}]
        for probe in cases:
            report=self.report(); report['pinProbe']=probe
            with self.subTest(probe=probe), self.assertRaises(ValueError):
                validate_report(report)
    def test_stopped_run_is_not_reported_as_completed(self):
        report=self.report(); report['pinProbe']={**self.probe(), 'completed':False}
        self.assertFalse(validate_report(report)['pinProbe']['completed'])

if __name__ == '__main__':
    unittest.main()
