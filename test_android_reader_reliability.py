"""Integration contracts for bounded streaming and targeted device navigation."""
from pathlib import Path
import unittest
BASE=Path(__file__).parent/'android_companion/app/src/main/java/ch/bob/degirocompanion'
class ReaderReliability(unittest.TestCase):
    def test_streaming_preserves_active_outbox_and_runs_only_after_persistence(self):
        transfer=(BASE/'ProductDetailDelivery.kt').read_text()
        stream=transfer.split('fun streamCurrent(',1)[1].split('private fun finish(',1)[0]
        self.assertNotIn('acknowledge(',stream)
        self.assertIn('PhoneDiagnostics.paired(c)',stream)
        self.assertIn('run.getInt("revision")',stream)
        self.assertIn('streamAgain=true;return',stream)
        run=(BASE/'MorningReadRun.kt').read_text().split('fun outcome(',1)[1]
        self.assertLess(run.index('event(c,finalCode)'),run.index('ProductDetailDelivery.streamCurrent(c)'))
        self.assertIn('if(MorningReadRun.running || !PhoneDiagnostics.paired(c))',transfer)
    def test_refresh_is_explicit_cancellable_bounded_and_reuses_login(self):
        activity=(BASE/'ProductReadActivity.kt').read_text()
        self.assertIn('selected.size in 1..3',activity)
        self.assertIn('ordered.all { it in selected }',activity)
        self.assertIn('refreshPreparing=false;statusHandler',activity)
        self.assertIn('if(!refreshTickets.accepts(refreshTicket) || !refreshPreparing || isFinishing || isDestroyed)',activity)
        self.assertIn('val refreshTicket=refreshTickets.issue()',activity)
        self.assertIn('refreshTickets.cancel();refreshPreparing=false',activity)
        self.assertIn('detailRefresh=intent',activity)
        self.assertIn('PhoneDiagnostics.keypadTestVerified(this)',activity)
        service=(BASE/'ProductReadService.kt').read_text()
        self.assertIn('detailRefresh.entries.associate { it.isin to it.missingFields },detailRefresh.listAt',service)
        self.assertIn('freshGold,detailRefresh)',service)
