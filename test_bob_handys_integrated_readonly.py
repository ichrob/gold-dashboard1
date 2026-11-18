"""Guard stable Bob Handy passive-DEGIRO integration and Samsung permission identity."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parent
JAVA=ROOT/"android_companion/app/src/main/java/ch/bob/degirocompanion"

class IntegratedReadOnlySecurityTests(unittest.TestCase):
    def test_stable_identity_no_new_accessibility_service_and_no_exported_entry(self):
        manifest=(ROOT/"android_companion/app/src/main/AndroidManifest.xml").read_text()
        gradle=(ROOT/"android_companion/app/build.gradle.kts").read_text()
        reader=(ROOT/"android_companion/app/src/main/res/xml/product_reader.xml").read_text()
        self.assertIn('applicationId = "ch.bob.degirocompanion.stable"',gradle)
        self.assertIn('android:name=".DegiroReadOnlyActivity" android:exported="false"',manifest)
        self.assertEqual(manifest.count('android:name=".ProductReadService"'),1)
        self.assertIn('android:packageNames="nl.degiro.trader"',reader)
    def test_readonly_no_action_and_no_pii_storage(self):
        policy=(JAVA/"DegiroStopLossReadOnly.kt").read_text()
        activity=(JAVA/"DegiroReadOnlyActivity.kt").read_text()
        service=(JAVA/"ProductReadService.kt").read_text()
        section=service.split("    // Explicit, passive, foreground-only DEGIRO form detection.")[1].split(
            "    // Only package/type metadata is used. Never read or retain event text.")[0]
        self.assertIn("DegiroStopLossReadOnly.inspect(snapshot)",section)
        for source in (policy,section):
            for prohibited in ("performAction(", "dispatchGesture(", "ACTION_CLICK",
                               "ACTION_SET_TEXT", "StopLossPrefillExecutor.execute",
                               "PhoneDiagnostics.queue(", "putString(",
                               "startActivity(", "HttpURLConnection"):
                self.assertNotIn(prohibited,source)
        self.assertIn('val caption=if(node.isEditable) ""',section)
        self.assertIn("ProductReadDiagnostics.connected",activity)
        self.assertIn('EXTRA_START_ONCE',activity)
        self.assertIn("Intent.createChooser",activity)
    def test_signed_main_app_has_its_own_one_tap_entry(self):
        main=(JAVA/"MainActivity.kt").read_text()
        self.assertIn("DEGIRO nur erkennen · 45 Sek.",main)
        self.assertIn("DegiroReadOnlyActivity.EXTRA_START_ONCE,true",main)

if __name__=="__main__":
    unittest.main()
