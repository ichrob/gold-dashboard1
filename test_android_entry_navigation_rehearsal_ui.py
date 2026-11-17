"""Source wiring regression for owner-triggered no-signal navigation rehearsal.

Actual Samsung accessibility/DEGIRO interaction still requires device testing.
This test is intentionally source-only; it never opens a live broker session or
writes simulated trading entries into production.
"""
from pathlib import Path
import unittest

BASE = Path(__file__).parent / "android_companion/app/src/main/java/ch/bob/degirocompanion"


def source(name):
    return (BASE / name).read_text()


class ImmediateEntryNavigation(unittest.TestCase):
    def test_entry_button_preserves_wait_for_signal_and_adds_separate_owner_test(self):
        activity = source("ProductReadActivity.kt")
        self.assertIn('button("Einstiegskurs automatisch nachlesen · 15 Minuten")', activity)
        self.assertIn('button("Einstiegskurs-Navigation sofort testen · ohne Signal")', activity)
        method = activity.split("private fun chooseEntryNavigationTest()", 1)[1].split(
            "private fun chooseQuoteRefresh()", 1
        )[0]
        self.assertIn("MorningReadRun.refreshSourceSnapshot(this)", method)
        self.assertIn('saved.optString("listBatchId")', method)
        self.assertIn("SeriesEvidence.validIsin(it)", method)
        self.assertIn('requestQuoteRefresh(saved,listOf(names[which]),testOnly=true)', method)
        for prohibited in (
            "PhoneRemote.start(", "MorningReadRun.beginDiscovered(",
            "GoldSearchRun.start(", "PinReadinessProbe.startLocalLogin(",
            "entry_read", "tradeApproved", "paper_trade", "createOrder",
        ):
            self.assertNotIn(prohibited, method, prohibited)

    def test_navigation_dialog_displays_isin_list_instead_of_message(self):
        activity = source("ProductReadActivity.kt")
        selection = activity.split("private fun chooseEntryNavigationTest()", 1)[1].split(
            "private fun chooseQuoteRefresh()", 1
        )[0]
        dialog = selection.split("AlertDialog.Builder(this)", 1)[1].split(
            '.setNegativeButton("Abbrechen"', 1
        )[0]
        self.assertIn('.setTitle("ISIN wählen · nur Lesetest")', dialog)
        self.assertIn(".setItems(names.toTypedArray())", dialog)
        # Android AlertController shows the message instead of the list when
        # both Builder.setMessage and Builder.setItems are set.
        self.assertNotIn(".setMessage(", dialog)

    def test_expired_list_does_not_fail_silently_and_offers_bounded_new_gold_read(self):
        activity = source("ProductReadActivity.kt")
        helper = activity.split("private fun showEntryNavigationStartProblem(", 1)[1].split(
            "private fun chooseEntryNavigationTest()", 1
        )[0]
        self.assertIn('setTitle("Navigationstest nicht gestartet")', helper)
        self.assertIn(".setMessage(message)", helper)
        self.assertIn('setPositiveButton("Goldliste jetzt einlesen")', helper)
        self.assertIn("startGoldRead()", helper)
        chooser = activity.split("private fun chooseEntryNavigationTest()", 1)[1].split(
            "private fun chooseQuoteRefresh()", 1
        )[0]
        self.assertIn("MorningReadRun.refreshSourceSnapshot(this)", chooser)
        self.assertIn("14*60*60*1000L", chooser)
        self.assertIn("freshListNeeded = true", chooser)
        self.assertIn("showEntryNavigationStartProblem(", chooser)
        self.assertIn("it.message ?: \"Navigationstest nicht verfügbar.\"", chooser)
        # Keep the original authenticated refresh and local read-only gates.
        self.assertIn("requestQuoteRefresh(saved,listOf(names[which]),testOnly=true)", chooser)
        self.assertNotIn("startGoldRead()", chooser)

    def test_refresh_rejections_are_modal_for_navigation_test_only(self):
        activity = source("ProductReadActivity.kt")
        method = activity.split("private fun requestQuoteRefresh(", 1)[1].split(
            "private fun startGoldRead()", 1
        )[0]
        self.assertEqual(method.count("if(testOnly) showEntryNavigationStartProblem(reason)"), 2)
        self.assertIn('PhoneDiagnostics.listStatus(app,org.json.JSONObject()', method)
        self.assertIn("if(LocalPinVault.exists(this))", method)
        self.assertIn("ProductReadRequest.start(SystemClock.elapsedRealtime())", method)

    def test_test_selection_always_one_and_reuses_real_owned_list_gate(self):
        activity = source("ProductReadActivity.kt")
        method = activity.split("private fun requestQuoteRefresh(", 1)[1].split(
            "private fun startGoldRead()", 1
        )[0]
        self.assertIn("if(testOnly) selected.size==1 else selected.size in 1..3", method)
        self.assertIn('PhoneDiagnostics.listStatus(app,org.json.JSONObject()', method)
        self.assertIn('put("batchId",saved.getString("listBatchId"))', method)
        self.assertIn('put("refreshIsins",org.json.JSONArray(selected))', method)
        self.assertIn('reply.optJSONObject("import")?.optString("stage")=="synced"', method)
        self.assertIn("SelectiveDetailPlan.parse", method)
        self.assertIn("if(PhoneRemote.active()) PhoneRemote.stop(this", method)
        self.assertIn("PinReadinessProbe.startLocalLogin(secret!!)", method)
        self.assertIn("MorningReadRun.beginDiscovered(this,ordered", method)
        self.assertIn("ProductReadRequest.start(SystemClock.elapsedRealtime())", method)
        self.assertIn("NAVIGATIONSTEST", method)
        self.assertNotIn("entryReadOnly=true", method)
        self.assertNotIn("entryApproved=true", method)
        self.assertNotIn("createOrder(", method)
        self.assertNotIn("placeOrder(", method)

    def test_signal_path_and_manual_test_share_guarded_android_navigator(self):
        service = source("ProductReadService.kt")
        self.assertIn('if(actionName=="entry_read")', service)
        self.assertIn("MorningReadRun.beginDiscovered(this,listOf(request.isin)", service)
        self.assertIn("ProductReadRequest.start(SystemClock.elapsedRealtime())", service)
        self.assertIn("if (MorningReadRun.running) {", service)
        self.assertIn("if (!MorningReadRun.reading && navigateMorning(root)) return", service)
        nav = service.split("private fun navigateMorning(", 1)[1]
        for required in (
            "MorningReadPolicy.detailDecision(", "MorningReadRun.target",
            "MorningReadPolicy.resultTapIndex(", "MorningReadPolicy.Kind.QUERY",
            "AccessibilityNodeInfo.ACTION_SET_TEXT", "MorningReadPolicy.Kind.BACK",
            "GLOBAL_ACTION_BACK", 'action.code=="PROTECTED_ORDER_CONFIRM"',
            "MorningReadRun.stop(this,action.code)",
        ):
            self.assertIn(required, nav, required)
        self.assertNotIn("ACTION_CLICK_ORDER", nav)

    def test_newer_confirmed_gold_source_wins_over_pinned_stale_batch(self):
        run = source("MorningReadRun.kt")
        self.assertIn("RefreshSourceChoice.choose(", run)
        self.assertIn('prefs(c).getString("refreshSource",null), latestSnapshot(c)', run)
        self.assertIn('data.optString("listBatchId").matches', run)
        self.assertIn('SeriesEvidence.validIsin(it)', run)
        self.assertIn('Instant.parse(data.getString("listUploadedAt"))', run)
        choice = source("RefreshSourceChoice.kt")
        self.assertIn(".maxByOrNull { it.first }?.second", choice)
        activity = source("ProductReadActivity.kt")
        self.assertIn('MorningReadRun.refreshSourceSnapshot(this)', activity)
        self.assertIn('14*60*60*1000L', activity)
        self.assertIn('PhoneDiagnostics.listStatus(app,org.json.JSONObject()', activity)

    def test_completed_last_product_sends_guarded_back_and_retains_result(self):
        service = source("ProductReadService.kt")
        final = service.split("// Final item: the original result is already durable.", 1)[1].split(
            "} else if(!backSent)", 1
        )[0]
        self.assertIn("FinalReadReturnPolicy.lastBackBlock(", final)
        self.assertIn("FINAL_BACK_BLOCK_SESSION", final)
        self.assertIn("FINAL_BACK_BLOCK_DEVICE", final)
        self.assertIn("FINAL_BACK_BLOCK_FOREGROUND", final)
        self.assertIn("FINAL_BACK_BLOCK_WINDOW", final)
        self.assertIn("FINAL_BACK_BLOCK_IDENTITY", final)
        self.assertIn("FINAL_BACK_BLOCK_SURFACE", final)
        self.assertIn("performGlobalAction(GLOBAL_ACTION_BACK)", final)
        self.assertIn('PhoneRemote.stop(this,"COMPLETED")', final)
        self.assertIn("MorningReadTransfer.automaticResults(this)", final)
        self.assertLess(final.index("performGlobalAction(GLOBAL_ACTION_BACK)"),
                        final.index('PhoneRemote.stop(this,"COMPLETED")'))
        self.assertLess(final.index("MorningReadTransfer.automaticResults(this)"),
                        final.index("startActivity(Intent(this,ProductReadActivity::class.java)"))
        for forbidden in ("createOrder(", "placeOrder(", "ACTION_CLICK_ORDER",
                          "ACTION_SET_TEXT", "ACTION_CLICK"):
            self.assertNotIn(forbidden, final)
        policy = source("FinalReadReturnPolicy.kt")
        self.assertIn("MorningReadPolicy.safeStatusReturn(nodes,expectedIsin)", policy)
        self.assertIn("MorningReadPolicy.returnAfterRead(nodes,expectedIsin", policy)
        self.assertIn("authorizedSession", policy)
        diagnostics = source("ProductReadDiagnostics.kt")
        for reason in ("FINAL_BACK_SENT", "FINAL_BACK_REJECTED", "FINAL_BACK_BLOCKED",
                       "FINAL_STATUS_REQUESTED", "FINAL_STATUS_FAILED"):
            self.assertIn(reason, diagnostics)

    def test_owner_screen_lock_rehearsal_is_no_signal_and_never_remote_entry(self):
        activity = source("ProductReadActivity.kt")
        self.assertIn('button("Samsung-Sperr-Fortsetzung sofort testen · ohne Signal")', activity)
        rehearsal = activity.split("private fun startOwnerUnlockRehearsal()", 1)[1].split(
            "private fun startAutomaticTest()", 1
        )[0]
        self.assertIn("!keyguard.isKeyguardLocked", rehearsal)
        self.assertIn("!keyguard.isDeviceLocked", rehearsal)
        self.assertIn("unlockRehearsalOnly=true", rehearsal)
        self.assertIn("resumeAfterOwnerUnlock=true", rehearsal)
        self.assertNotIn("startGoldRead()", rehearsal)
        self.assertNotIn("MorningReadRun.beginDiscovered", rehearsal)
        self.assertNotIn("placeOrder(", rehearsal)
        remote = source("PhoneRemote.kt")
        self.assertIn("private var unlockRehearsalOnly=false", remote)
        self.assertIn("entryOnly && !waitingOnUnlock && !unlockRehearsalOnly", remote)
        self.assertIn('if(unlockRehearsalOnly) empty("UNLOCK_TEST_ARMED")', remote)
        self.assertIn('if(unlockRehearsalOnly && !rehearsalOwnerPresent)return false', remote)
        self.assertIn('fun noteOwnerPresentForUnlockTest()', remote)
        self.assertIn('if(!unlockRehearsalOnly)response.optJSONObject("command")', remote)
        self.assertIn('stop(c,"UNLOCK_TEST_CONFIRMED")', remote)
        self.assertIn('if(unlockRehearsalOnly) 180000L else 900000L', remote)
        self.assertIn('else if(entryOnly && !unlockRehearsalOnly)"entry_read" else "product_read"', remote)
        service = source("ProductReadService.kt")
        self.assertIn("PhoneRemote.pauseForScreenLock(inProgress)", service)
        self.assertIn("PhoneRemote.noteOwnerPresentForUnlockTest()", service)
        self.assertIn("resumeEntryAfterOwnerUnlock()", service)
        self.assertIn("keyguard.isDeviceLocked", service)
        diag = source("ProductReadDiagnostics.kt")
        for flag in ("UNLOCK_TEST_ARMED", "UNLOCK_TEST_WAITING",
                     "UNLOCK_TEST_CONFIRMED", "UNLOCK_TEST_EXPIRED"):
            self.assertIn(flag, diag)

    def test_terminal_list_product_can_be_skipped_but_no_trade_is_approved(self):
        server = Path(__file__).parent.joinpath("android_list.py").read_text()
        self.assertIn("refresh_plan(row[1] or [],products,selected,terminal_isins)", server)
        self.assertIn('row[0].get(\'stage\')==\'synced\'', server)
        self.assertIn("Owned list expired for targeted refresh", server)
        read_run = source("MorningReadRun.kt")
        self.assertIn("if(requested!=null) check(requested.keys==values.toSet()", read_run)
        self.assertIn("ProductDetailDelivery.streamCurrent(c)", read_run)


if __name__ == "__main__":
    unittest.main()
