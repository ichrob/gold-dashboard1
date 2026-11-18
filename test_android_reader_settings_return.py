"""Regression guards for Samsung's nested accessibility settings return path.

The device owns its settings/back stack. Bob must avoid launching those pages
when its ProductReadService is already enabled, without granting phone control
from an Android shortcut toggle or auto-starting DEGIRO on resume.
"""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parent /
          "android_companion/app/src/main/java/ch/bob/degirocompanion/ProductReadActivity.kt")


class ReaderSettingsReturn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = SOURCE.read_text(encoding="utf-8")

    def test_enabled_read_service_stays_in_bob_not_nested_samsung_settings(self):
        code = self.code
        dialog = code.split('button("Leseprüfung einschalten / Android-Einstellungen")', 1)[1]
        dialog = dialog.split('container.addView(android.widget.CheckBox', 1)[0]
        self.assertIn('if(serviceEnabled()) {', dialog)
        self.assertLess(dialog.index('if(serviceEnabled()) {'),
                        dialog.index('startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))'))
        self.assertIn('preferences.edit().putBoolean("enabled", true).apply()', dialog)
        self.assertIn('Hier bleiben und oben „Bob starten“ drücken.', dialog)
        self.assertIn('readerSettingsOpened = true', dialog)
        self.assertIn('readerScroll.post { readerScroll.scrollTo(0, 0) }', dialog)
        self.assertIn('readerScroll = scroll', code)

    def test_real_product_reader_not_shortcut_is_source_of_truth(self):
        code = self.code
        service = code.split('private fun serviceEnabled(): Boolean {', 1)[1].split('private fun refresh()', 1)[0]
        self.assertIn('ProductReadService::class.java.name', service)
        self.assertIn('getEnabledAccessibilityServiceList', service)
        self.assertNotIn('Shortcut', service)
        self.assertIn('Shortcut allein genügt nicht', code)

    def test_bob_start_can_request_local_opt_in_without_reopening_samsung(self):
        code = self.code
        start = code.split('private fun startAutomaticTest() {', 1)[1].split('private fun primaryAction()', 1)[0]
        self.assertIn('if(serviceEnabled() && !preferences.getBoolean("enabled", false))', start)
        self.assertIn('setPositiveButton("Freigeben und Bob starten")', start)
        self.assertIn('preferences.edit().putBoolean("enabled", true).commit()', start)
        self.assertIn('startAutomaticTest()', start)
        self.assertIn('Keine Orders und keine Umgehung der Samsung-Sperre.', start)
        self.assertNotIn('Settings.ACTION_ACCESSIBILITY_SETTINGS', start)

    def test_saved_morning_list_button_also_stays_out_of_samsung_when_enabled(self):
        code = self.code
        action = code.split('private fun primaryAction() {', 1)[1].split(
            'private fun serviceEnabled(): Boolean {', 1)[0]
        self.assertIn('MorningReadUiPolicy.Action.SETUP -> {', action)
        self.assertIn('if(serviceEnabled()) {', action)
        self.assertIn('readerScroll.post { readerScroll.scrollTo(0, 0) }', action)
        self.assertIn('readerSettingsOpened = true', action)
        self.assertIn('Settings.ACTION_ACCESSIBILITY_SETTINGS', action)

    def test_return_never_triggers_broker_navigation_without_owner_tap(self):
        code = self.code
        resume = code.split('override fun onResume() {', 1)[1].split('override fun onPause()', 1)[0]
        self.assertIn('if(readerSettingsOpened)', resume)
        self.assertIn('readerSettingsOpened = false', resume)
        after_settings = resume.split('if(readerSettingsOpened)', 1)[1].split('statusHandler.post(statusTick)', 1)[0]
        self.assertNotIn('startAutomaticTest()', after_settings)
        self.assertNotIn('startGoldRead()', after_settings)
        self.assertIn('serviceEnabled()', after_settings)
        self.assertIn('Oben „Bob starten“ drücken', after_settings)
        self.assertIn('startCompleteFlowOnFirstResume = false', resume)


if __name__ == "__main__":
    unittest.main()
