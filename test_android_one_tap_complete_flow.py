"""Static integration guards for Bob Handy single-tap read-only DEGIRO flow.

These tests complement, not replace, the JVM policy suite and real Samsung test.
"""
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
APP = ROOT / "android_companion/app/src/main"
SRC = APP / "java/ch/bob/degirocompanion"


def source(name):
    return (SRC / name).read_text(encoding="utf-8")


class OneTapCompleteFlowTest(unittest.TestCase):
    def test_main_home_has_one_explicit_complete_flow_button(self):
        main = source("MainActivity.kt")
        self.assertIn('button("▶ Bob starten · DEGIRO, Gold und fehlende Werte")', main)
        self.assertIn('.putExtra(ProductReadActivity.EXTRA_START_COMPLETE_FLOW, true)', main)
        self.assertIn('button("DEGIRO-Leser · Einrichtung und Einzelprüfungen")', main)

    def test_one_shot_only_from_internal_unexported_activity(self):
        manifest = (APP / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:name=".ProductReadActivity" android:exported="false"', manifest)
        activity = source("ProductReadActivity.kt")
        self.assertIn('savedInstanceState == null &&', activity)
        self.assertIn('intent.getBooleanExtra(EXTRA_START_COMPLETE_FLOW, false)', activity)
        self.assertIn('intent.removeExtra(EXTRA_START_COMPLETE_FLOW)', activity)
        self.assertIn("startCompleteFlowOnFirstResume = false\n            startAutomaticTest()", activity)
        resume = activity.split('override fun onResume()', 1)[1].split('override fun onPause()', 1)[0]
        self.assertLess(resume.index('PinReadinessProbe.stop('),
                        resume.index('startAutomaticTest()'))

    def test_login_and_follow_up_are_bounded_and_no_pin_leaves_device(self):
        activity = source("ProductReadActivity.kt")
        service = source("ProductReadService.kt")
        handoff = source("LoginToReadHandoff.kt")
        self.assertIn('LocalPinVault.load(this)', activity)
        self.assertIn('PinReadinessProbe.startLocalLogin(localPin!!)', activity)
        self.assertIn('localPin?.fill(0)', activity)
        self.assertIn('code == "LOCAL_PIN_HOME_VISIBLE"', handoff)
        self.assertIn('if (proceed) handler.post', service)
        self.assertIn('GoldSearchRun.start()', service)
        self.assertIn('MorningReadRun.beginDiscovered(this,plan.map { it.isin },batch,', service)
        self.assertIn('plan.associate { it.isin to it.missingFields }', service)

    def test_gold_button_uses_local_login_before_starting_full_reader(self):
        method = source("ProductReadActivity.kt").split('private fun startGoldRead()', 1)[1].split('/** One explicit start:', 1)[0]
        self.assertLess(method.index('PinReadinessProbe.startLocalLogin'), method.index('GoldSearchRun.start()'))
        self.assertIn('freshGold=true', method)
        self.assertIn('return@runCatching', method)
        self.assertIn('localPin?.fill(0)', method)
        self.assertIn('PhoneDiagnostics.keypadTestVerified(this)', method)
        self.assertIn('!PinReadinessProbe.running', method)
        service = source("ProductReadService.kt")
        self.assertIn('freshGold || !MorningReadRun.resumeRecent(this)', service)
        self.assertRegex(service,
            r'attempt\+1,searchQuery,ticket,\s*sessionOnly,freshGold,detailRefresh,entryReadOnly')
        self.assertIn('if (!sessionOnly) {', service)
        self.assertIn('else if(freshGold || !MorningReadRun.resumeRecent(this)) GoldSearchRun.start()', service)

    def test_verified_gold_footer_photo_precedes_phantom_webview_scroll(self):
        # Regression from the original Samsung 10/10 Gold-list workflow.
        # DEGIRO may advertise ACTION_SCROLL_FORWARD at the real footer.
        # Do not lose a fourth original image to an ineffective scroll.
        service = source("ProductReadService.kt")
        capture = service.split("private fun captureMorningList(", 1)[1].split(
            "private fun deliverMorningList(", 1)[0]
        self.assertIn("MorningListEndPolicy.needsFooterRecapture(", capture)
        self.assertIn("val footerFirst=root.windowId==listWindowId", capture)
        self.assertIn("val candidates=if(footerFirst) emptyList() else nodes.indices.filter", capture)
        self.assertLess(capture.index("val footerFirst="), capture.index("val candidates="))
        self.assertLess(capture.index("val candidates="), capture.index("val chosen="))
        # The fourth picture cannot bypass the original ten-row server gate.
        delivery = source("MorningListDelivery.kt")
        self.assertIn('receipt?.optString("stage")=="synced"', delivery)
        self.assertIn('receipt.optInt("count")==10', delivery)
        self.assertIn("onConfirmed?.invoke(plan,batch)", delivery)
        self.assertIn("MorningReadRun.beginDiscovered(this,plan.map { it.isin },batch,", service)

    def test_rejected_list_shows_redacted_row_count_but_never_confirms(self):
        delivery = source("MorningListDelivery.kt")
        self.assertIn("internal fun rejectedListHint(", delivery)
        self.assertIn("counts.optInt(\"uniqueRows\",-1)", delivery)
        self.assertIn("Keine Produktfreigabe.", delivery)
        self.assertIn("rejectedListHint(receipt)", delivery)
        self.assertIn("terminalVerificationFailed(", delivery)

    def test_list_receipt_is_not_detail_success(self):
        delivery = source("MorningListDelivery.kt")
        self.assertIn('receipt.optInt("count")==10', delivery)
        self.assertIn('plan!=null && plan.isNotEmpty()', delivery)
        self.assertIn('Detailplan nicht verifizierbar; Nachlesen gestoppt.', delivery)
        self.assertIn('Keine fehlenden Felder für einen neuen Detail-Leselauf.', delivery)


if __name__ == "__main__":
    unittest.main()
