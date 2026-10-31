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

    def test_market_gate_status_strictly_sanitized_and_local_login_only(self):
        from android_telemetry import PIN_MARKET_STATUSES
        for status in PIN_MARKET_STATUSES:
            report=dict(self.report(),pinProbe=dict(self.probe(),
                result='LOCAL_PIN_RESULT_UNVERIFIED',marketStatus=status))
            self.assertEqual(validate_report(report)['pinProbe']['marketStatus'],status)
        bad=('Mit Namen, ISIN oder Symbol suchen', 'CHF 504,74',
             'MARKETS_LOGIN_SUCCESS', '', None, [], 1)
        for status in bad:
            report=dict(self.report(),pinProbe=dict(self.probe(),
                result='LOCAL_PIN_RESULT_UNVERIFIED',marketStatus=status))
            with self.subTest(status=status), self.assertRaises(ValueError):
                validate_report(report)
        report=dict(self.report(),pinProbe=dict(self.probe(),
            result='KEYPAD_TEST_INTERRUPTED',marketStatus='VERIFIED'))
        with self.assertRaises(ValueError): validate_report(report)

    def test_market_status_enum_contract_matches_android(self):
        import re
        from pathlib import Path
        from android_telemetry import PIN_MARKET_STATUSES
        source=(Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion/LocalLoginDialogs.kt').read_text()
        block=re.search(r'enum class MarketStatus\s*\{([^}]+)',source).group(1)
        self.assertEqual(set(re.findall(r'\b[A-Z_]+\b',block)),PIN_MARKET_STATUSES)

    def test_dialog_outcomes_contain_no_screen_text_or_credentials(self):
        for result in ('LOCAL_PIN_HOME_VISIBLE', 'LOCAL_PIN_DIALOG_UNCHANGED',
                       'LOCAL_PIN_DIALOG_UNRECOGNIZED', 'LOCAL_PIN_DIALOG_BLOCKED',
                       'LOCAL_PIN_DIALOG_REPEATED', 'LOCAL_PIN_DIALOG_ACTION_FAILED'):
            report = dict(self.report(), pinProbe=dict(self.probe(), result=result))
            self.assertEqual(validate_report(report)['pinProbe']['result'], result)
            for extra in ({'dialogText':'synthetic'}, {'pin':'synthetic'}, {'bounds':[1,2,3,4]}):
                with self.assertRaises(ValueError):
                    validate_report(dict(report, pinProbe=report['pinProbe'] | extra))

    def dialog_check(self, **changes):
        return dict(phase='BEFORE_PIN', owner='SAMSUNG_BIOMETRICS', stage='MARKER_CHECK',
                    systemVerified=True, degiroContext=False, degiroLabel=False,
                    biometricLabel=True, cancelLabel=True, cancelAmbiguous=False) | changes

    def test_dialog_check_roundtrip_and_owner_vs_marker_distinction(self):
        from android_telemetry import PIN_DIALOG_BOOLS
        cases=[self.dialog_check(), self.dialog_check(owner='DEGIRO', systemVerified=False, degiroContext=True),
               self.dialog_check(owner='OTHER', stage='OWNER_CHECK', **{k:False for k in PIN_DIALOG_BOOLS}),
               self.dialog_check(cancelLabel=False, cancelAmbiguous=True, phase='AFTER_PIN')]
        for check in cases:
            report=dict(self.report(), pinProbe=dict(self.probe(), result='LOCAL_PIN_DIALOG_UNRECOGNIZED', dialogCheck=check))
            with self.subTest(check=check):
                self.assertEqual(validate_report(report)['pinProbe']['dialogCheck'], check)

    def test_dialog_check_rejects_text_credentials_bad_types_and_inconsistent_evidence(self):
        from android_telemetry import validate_pin_dialog_check
        bad=[self.dialog_check(text='private'), self.dialog_check(pin='synthetic'),
             self.dialog_check(packageName='arbitrary'), self.dialog_check(bounds=[1,2,3,4]),
             self.dialog_check(owner='arbitrary'), self.dialog_check(phase=[]), self.dialog_check(stage=0),
             self.dialog_check(systemVerified=1), self.dialog_check(cancelLabel='true'),
             self.dialog_check(stage='OWNER_CHECK'), self.dialog_check(owner='OTHER'),
             self.dialog_check(systemVerified=False), self.dialog_check(cancelAmbiguous=True),
             self.dialog_check(owner='DEGIRO', degiroContext=True), {}, [], None]
        for check in bad:
            with self.subTest(check=check), self.assertRaises(ValueError):
                validate_pin_dialog_check(check, 'LOCAL_PIN_DIALOG_UNRECOGNIZED')
        for result in ('LOCAL_PIN_HOME_VISIBLE', 'LOCAL_PIN_ENTRY_SENT', 'LOCAL_PIN_WAITING', 'LOCAL_PIN_DIALOG_BLOCKED'):
            with self.subTest(result=result), self.assertRaises(ValueError):
                validate_pin_dialog_check(self.dialog_check(), result)
        report=dict(self.report(), pinProbe=dict(self.probe(), result='LOCAL_PIN_DIALOG_UNRECOGNIZED',
                    dialogCheck=self.dialog_check(), symbolFlags=self.flags()))
        with self.assertRaises(ValueError): validate_report(report)

    def test_owner_context_is_optional_strict_metadata_and_owner_failure_only(self):
        from android_telemetry import validate_pin_dialog_check, PIN_DIALOG_BOOLS
        base = self.dialog_check(owner='OTHER', stage='OWNER_CHECK', **{k:False for k in PIN_DIALOG_BOOLS})
        context = dict(rootKind='BOB', focusedKind='DEGIRO', sameWindow=False, fingerprintProgress='NOT_REQUESTED')
        self.assertEqual(validate_pin_dialog_check(base, 'LOCAL_PIN_DIALOG_UNRECOGNIZED'), base)
        for kind in ('EMPTY', 'BOB', 'ANDROID_FRAMEWORK', 'PERMISSION_CONTROLLER', 'OTHER'):
            check = base | {'ownerContext':context | {'rootKind':kind}}
            self.assertEqual(validate_pin_dialog_check(check, 'LOCAL_PIN_DIALOG_UNRECOGNIZED'), check)
        for progress in ('NOT_REQUESTED', 'REQUESTED', 'ACCEPTED_WAIT', 'ACCEPTED_EXPIRED', 'RETURNED'):
            validate_pin_dialog_check(base | {'ownerContext': context | {'fingerprintProgress':progress}},
                                      'LOCAL_PIN_DIALOG_UNRECOGNIZED')
        invalid = [None, [], {}, context | {'pin':'synthetic'}, context | {'packageName':'private'},
                   context | {'text':'private'}, context | {'rootKind':'nl.degiro.trader'},
                   context | {'rootKind':'UNAVAILABLE'}, context | {'rootKind':'AMBIGUOUS'},
                   context | {'rootKind':'DEGIRO'}, context | {'rootKind':'SYSTEM_UI'},
                   context | {'focusedKind':[]}, context | {'fingerprintProgress':'SUCCESS'},
                   context | {'sameWindow':1}, context | {'sameWindow':True, 'focusedKind':'AMBIGUOUS'}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_pin_dialog_check(base | {'ownerContext':value}, 'LOCAL_PIN_DIALOG_UNRECOGNIZED')
        with self.assertRaises(ValueError):
            validate_pin_dialog_check(self.dialog_check() | {'ownerContext':context}, 'LOCAL_PIN_DIALOG_UNRECOGNIZED')

    def test_rejected_package_metadata_is_bounded_optional_and_not_click_authority(self):
        from android_telemetry import validate_pin_dialog_check, PIN_DIALOG_BOOLS, PIN_DIALOG_PACKAGE_RESOLUTIONS
        base = self.dialog_check(owner='OTHER', stage='OWNER_CHECK', **{k:False for k in PIN_DIALOG_BOOLS})
        context = dict(rootKind='OTHER', focusedKind='UNAVAILABLE', sameWindow=True, fingerprintProgress='RETURNED')
        for resolution in PIN_DIALOG_PACKAGE_RESOLUTIONS:
            check = base | {'ownerContext':context | {'packageEvidence':dict(name='com.example.dialog', resolution=resolution)}}
            report = dict(self.report(), pinProbe=dict(self.probe(), result='LOCAL_PIN_DIALOG_UNRECOGNIZED', dialogCheck=check))
            self.assertEqual(validate_report(report)['pinProbe']['dialogCheck'], check)
        valid = dict(name='com.example.dialog', resolution='NOT_RESOLVED')
        invalid = [None, [], {}, valid | {'text':'private'}, valid | {'pin':'synthetic'},
                   valid | {'resolution':1}, valid | {'resolution':'TRUSTED_FOR_CLICK'}]
        invalid += [valid | {'name':name} for name in (None, [], '', '12345', 'Schließen',
                    'user@example.test', 'com.example app', 'com.example\n', 'com..example', 'com.1example',
                    'com.' + 'a'*201, 'a.'*17+'a')]
        for evidence in invalid:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                validate_pin_dialog_check(base | {'ownerContext':context | {'packageEvidence':evidence}}, 'LOCAL_PIN_DIALOG_UNRECOGNIZED')
        for root_kind in ('BOB', 'EMPTY', 'ANDROID_FRAMEWORK'):
            with self.subTest(root_kind=root_kind), self.assertRaises(ValueError):
                validate_pin_dialog_check(base | {'ownerContext':context | {'rootKind':root_kind, 'packageEvidence':valid}}, 'LOCAL_PIN_DIALOG_UNRECOGNIZED')

    def test_prior_degiro_scan_survives_later_owner_failure_without_screen_text(self):
        from android_telemetry import validate_pin_dialog_check, PIN_DIALOG_BOOLS, PIN_DIALOG_DEGIRO_SCANS
        base = self.dialog_check(owner='OTHER', stage='OWNER_CHECK', **{k:False for k in PIN_DIALOG_BOOLS})
        context = dict(rootKind='OTHER', focusedKind='OTHER', sameWindow=True, fingerprintProgress='RETURNED')
        for stage in PIN_DIALOG_DEGIRO_SCANS:
            for extra in ({}, {'packageEvidence':dict(name='com.example.launcher', resolution='INSTALLED_SYSTEM')}):
                check = base | {'ownerContext':context | {'lastDegiroScan':stage} | extra}
                self.assertEqual(validate_pin_dialog_check(check, 'LOCAL_PIN_DIALOG_UNRECOGNIZED'), check)
        for stage in (None, 1, [], 'Schließen', 'LOGIN_SUCCESS'):
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                validate_pin_dialog_check(base | {'ownerContext':context | {'lastDegiroScan':stage}}, 'LOCAL_PIN_DIALOG_UNRECOGNIZED')

    def test_scan_stage_enum_contract_matches_android(self):
        import re
        from pathlib import Path
        from android_telemetry import PIN_DIALOG_DEGIRO_SCANS
        source=(Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion/LoginDialogPolicy.kt').read_text()
        block=re.search(r'enum class DegiroScan\s*\{([^}]+)', source).group(1)
        self.assertEqual(set(re.findall(r'\b[A-Z_]+\b', block)), PIN_DIALOG_DEGIRO_SCANS)

    def test_package_resolution_enum_contract_matches_android(self):
        import re
        from pathlib import Path
        from android_telemetry import PIN_DIALOG_PACKAGE_RESOLUTIONS
        source=(Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion/LoginDialogPolicy.kt').read_text()
        block=re.search(r'enum class Resolution\s*\{([^}]+)', source).group(1)
        self.assertEqual(set(re.findall(r'\b[A-Z_]+\b', block)), PIN_DIALOG_PACKAGE_RESOLUTIONS)

    def test_owner_context_enum_contract_matches_android(self):
        import re
        from pathlib import Path
        from android_telemetry import PIN_DIALOG_ROOT_KINDS, PIN_DIALOG_FINGERPRINT_PROGRESS
        source=(Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion/LoginDialogPolicy.kt').read_text()
        for name, expected in [('RootKind', PIN_DIALOG_ROOT_KINDS), ('FingerprintProgress', PIN_DIALOG_FINGERPRINT_PROGRESS)]:
            block=re.search(r'enum class '+name+r'\s*\{([^}]+)', source).group(1)
            self.assertEqual(set(re.findall(r'\b[A-Z_]+\b', block)), set(expected))

    def test_dialog_check_enum_contract_matches_android(self):
        import re
        from pathlib import Path
        from android_telemetry import PIN_DIALOG_PHASES, PIN_DIALOG_OWNERS, PIN_DIALOG_STAGES
        source=(Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion/LoginDialogPolicy.kt').read_text()
        for name, expected in [('Phase', PIN_DIALOG_PHASES), ('Owner', PIN_DIALOG_OWNERS), ('Stage', PIN_DIALOG_STAGES)]:
            block=re.search(r'enum class '+name+r'\s*\{([^}]+)', source).group(1)
            self.assertEqual(set(re.findall(r'\b[A-Z_]+\b', block)), set(expected))

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
