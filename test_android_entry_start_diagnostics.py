"""Preflight privacy and wire regression; physical Samsung acceptance is separate."""
import re
import unittest
from pathlib import Path
import android_telemetry
from test_android_telemetry import report

ROOT = Path('android_companion/app/src/main/java/ch/bob/degirocompanion')

class EntryStartDiagnosticsTests(unittest.TestCase):
    def test_all_app_preflight_and_handoff_codes_are_accepted_without_private_fields(self):
        codes = set(re.findall(r'ENTRY_START_[A-Z_]+', (ROOT/'EntryReadStartPolicy.kt').read_text()))
        codes |= set(re.findall(r'LOGIN_HANDOFF_[A-Z_]+', (ROOT/'ProductReadService.kt').read_text()))
        self.assertGreaterEqual(len(codes),14)
        for code in codes:
            with self.subTest(code=code):
                value=report();value['lastCode']=code
                self.assertEqual(code,android_telemetry.validate_report(value)['lastCode'])
                for extra in ('pin','password','account','exception','screenText'):
                    with self.assertRaises(ValueError):
                        android_telemetry.validate_report(dict(value,**{extra:'private'}))
        value=report();value['lastCode']='ENTRY_START_private_content'
        with self.assertRaises(ValueError):android_telemetry.validate_report(value)

    def test_idle_session_stops_before_login_and_failure_preserves_other_handoff(self):
        body=(ROOT/'ProductReadActivity.kt').read_text().split('button("Einstiegskurs automatisch',1)[1].split('button("ChatGPT-Handy',1)[0]
        self.assertNotIn('!PhoneRemote.active()',body)
        self.assertLess(body.index('mayReplaceIdleSession('),body.index('PhoneRemote.stop('))
        self.assertLess(body.index('LocalPinVault.load(this)'),body.index('PhoneRemote.stop('))
        self.assertLess(body.index('PhoneRemote.stop('),body.index('LoginToReadHandoff.arm('))
        failure=body.split('}.onFailure {',1)[1]
        self.assertIn('if(loginStarted) LoginToReadHandoff.clear()',failure)
        self.assertIn('recordEntryStartFailure(this,failureCode)',failure)
        self.assertIn('secret?.fill(0)',failure)
        recorder=(ROOT/'PhoneDiagnostics.kt').read_text().split('fun recordEntryStartFailure(',1)[1].split('fun snapshot(',1)[0]
        self.assertIn('if(!enabled(c))return',recorder)
        self.assertLess(recorder.index('.commit()'),recorder.index('queue(c)'))
        self.assertNotIn('Throwable',recorder)
