"""Regression: November paper accounts and recorded entry gates remain visible.

These assertions cover only the authenticated read-only UI contract; they do
not fabricate historical executions or weaken any paper/trading guard.
"""
import unittest

from vollautomatisch_panel import PANEL


class NovemberPaperVisibilityTests(unittest.TestCase):
    def test_nine_account_contract_and_separate_november_profiles(self):
        self.assertIn("data.mode!=='independent-prospective-paper-accounts'", PANEL)
        self.assertIn("data.accounts.length!==9", PANEL)
        self.assertIn("'trend800nov','normal1000nov'", PANEL)
        self.assertIn("trend800nov:'Neu · 800 € Trend/Stopp/Wiedereinstieg'", PANEL)
        self.assertIn("normal1000nov:'Neu · 1.000 € bestätigtes Hauptsignal'", PANEL)
        self.assertNotIn("data.mode!=='seven-independent-paper-accounts'", PANEL)
        self.assertNotIn("data.accounts.length!==7", PANEL)

    def test_display_uses_only_persisted_daily_entry_blocks(self):
        self.assertIn("st.lastWait||c.reason", PANEL)
        self.assertIn("st.entryBlockCounts||{}", PANEL)
        self.assertIn("st.entryBlocksTruncated", PANEL)
        self.assertIn("Prüfungen, nicht verpasste Trades", PANEL)
        self.assertIn("ältere Tageszeiten nicht rückwirkend belegbar", PANEL)
        self.assertIn("data.realOrders!==false", PANEL)
        self.assertNotIn("new_case(", PANEL)
        self.assertNotIn("place_order(", PANEL)

    def test_relaunch_comparison_makes_no_unsupported_winner_claim(self):
        self.assertIn("data.relaunchComparison", PANEL)
        self.assertIn("comparison.comparableModelClosures===true", PANEL)
        self.assertIn("Keine bestätigten Nettogewinne oder Echtgeldorders.", PANEL)


if __name__ == '__main__':
    unittest.main()
