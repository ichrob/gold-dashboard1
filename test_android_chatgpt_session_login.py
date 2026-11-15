"""Wiring checks complement the JVM handoff tests; not a device login proof."""
import unittest
from pathlib import Path
ROOT = Path('android_companion/app/src/main/java/ch/bob/degirocompanion')
class SessionLoginTests(unittest.TestCase):
    def test_explicit_button_uses_local_login_and_clears_secret(self):
        s = (ROOT/'ProductReadActivity.kt').read_text()
        button = s.split('button("ChatGPT-Handy-Sitzung starten',1)[1].split('button(',1)[0]
        self.assertIn('startChatGptSession()', button)
        method = s.split('private fun startChatGptSession()',1)[1].split('/** Shared prerequisites',1)[0]
        self.assertIn('startAutomaticTest()', method)
        self.assertIn('if (readerBusy)', method)
        self.assertIn('ProductReadRequest.active', method)
        self.assertIn('LoginToReadHandoff.pending', method)
        self.assertLess(method.index('if (readerBusy)'), method.index('PhoneRemote.stop'))
        self.assertNotIn('sessionOnly = true', method)
        automatic = s.split('private fun startAutomaticTest()',1)[1].split('private fun primaryAction()',1)[0]
        for guard in ('keypadTestVerified(this)', 'LocalPinVault.available(this)',
                      'PhoneDiagnostics.paired(this)', 'LoginToReadHandoff.arm(SystemClock.elapsedRealtime())',
                      'PinReadinessProbe.startLocalLogin(localPin!!)', 'localPin?.fill(0)',
                      'GoldSearchRun.start()', 'MorningReadRun.resumeRecent(this)'):
            self.assertIn(guard, automatic)
    def test_handoff_preserves_session_only_across_retry_and_consume(self):
        s = (ROOT/'ProductReadService.kt').read_text()
        self.assertIn('beginReadAfterVerifiedPin(attempt+1,searchQuery,ticket,sessionOnly,freshGold,detailRefresh)',s)
        self.assertIn('beginReadAfterVerifiedPin(0,searchQuery,ticket,sessionOnly,freshGold,detailRefresh)',s)
        self.assertLess(s.index('val sessionOnly = LoginToReadHandoff.sessionOnly'), s.index('LoginToReadHandoff.consume('))
        body = s.split('private fun beginReadAfterVerifiedPin',1)[1].split('override fun onServiceConnected',1)[0]
        self.assertIn('if (!sessionOnly) {',body)
        self.assertIn('check(PhoneRemote.active())',body)
