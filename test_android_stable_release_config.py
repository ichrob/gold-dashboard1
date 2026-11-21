"""Static regression: stable Android signing/update policy never backslides.

No secrets, keystores, builds, browser or device access is needed for this test.
"""
import unittest
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
GRADLE = ROOT / "android_companion/app/build.gradle.kts"
DEBUG = ROOT / ".github/workflows/android-companion.yml"
RELEASE = ROOT / ".github/workflows/android-stable-release.yml"
MANIFEST = ROOT / "android_companion/app/src/main/AndroidManifest.xml"


class AndroidStableReleaseTests(unittest.TestCase):
    def test_one_permanent_identity_and_isolated_debug_app(self):
        gradle = GRADLE.read_text(encoding="utf-8")
        self.assertIn('applicationId = "ch.bob.degirocompanion.stable"', gradle)
        self.assertIn('applicationIdSuffix = ".voicetest"', gradle)
        self.assertIn('versionCode = System.getenv("BOB_ANDROID_VERSION_CODE")', gradle)
        self.assertIn('signingConfigs.getByName("bobStable")', gradle)
        self.assertIn('if (bobHasSigning)', gradle)
        self.assertIn('manifestPlaceholders["bobAppLabel"] = "Bob – Handy"', gradle)
        self.assertNotIn('applicationIdSuffix = ".parallel"', gradle)

    def test_release_requires_main_ci_and_configured_pinned_signing(self):
        workflow = RELEASE.read_text(encoding="utf-8")
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn('workflow_run:', workflow)
        self.assertIn('workflows: ["Bob CI"]', workflow)
        self.assertIn('types: [completed]', workflow)
        self.assertIn('branches: [main]', workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.event.workflow_run.event == 'push'", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.head_sha == github.sha", workflow)
        self.assertIn('jq -r \'.workflow_run.head_sha\'', workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', workflow)
        self.assertIn('git merge-base --is-ancestor "$last_tag" HEAD', workflow)
        self.assertIn('git diff --name-only "$last_tag" HEAD', workflow)
        self.assertIn('android_companion/app/', workflow)
        self.assertIn('needs_release=false', workflow)
        self.assertIn('needs_release=true', workflow)
        self.assertGreaterEqual(
            workflow.count("if: steps.update.outputs.needs_release == 'true'"), 7)
        self.assertIn('conclusion', workflow)
        self.assertIn('grep -Fxq "$GITHUB_SHA"', workflow)
        self.assertIn('BOB_ANDROID_KEYSTORE_BASE64', workflow)
        self.assertIn('BOB_ANDROID_STORE_PASSWORD', workflow)
        self.assertIn('BOB_ANDROID_KEY_PASSWORD', workflow)
        self.assertIn('BOB_ANDROID_CERT_SHA256', workflow)
        self.assertIn('BOB_ANDROID_PUBLIC_CERT_SHA256=', workflow)
        self.assertIn('vars.BOB_ANDROID_CERT_SHA256', workflow)
        self.assertNotIn('BOB_ANDROID_PRIVATE_KEY=', workflow)
        self.assertIn('apksigner', workflow)
        self.assertIn('if [ "$actual" != "$expected" ]', workflow)
        self.assertIn("ch.bob.degirocompanion.stable", workflow)
        self.assertIn("gh release create", workflow)
        # gh 'file#label' changes the label, not the downloadable asset name.
        self.assertIn('staged="$RUNNER_TEMP/Bob-Handy.apk"', workflow)
        self.assertIn('cp -- "$apk" "$staged"', workflow)
        self.assertIn('cmp -- "$apk" "$staged"', workflow)
        self.assertIn('gh release view "$tag" --repo "$GITHUB_REPOSITORY" --json assets', workflow)
        self.assertNotIn('app-release.apk#Bob-Handy.apk', workflow)
        self.assertIn("rm -f", workflow)
        self.assertNotIn("pull_request:", workflow)

    def test_network_trust_is_limited_to_exact_bob_host(self):
        import xml.etree.ElementTree as ET
        root=ET.parse(ROOT / "android_companion/app/src/main/res/xml/diagnostic_network.xml").getroot()
        base=root.find('base-config')
        self.assertEqual(base.get('cleartextTrafficPermitted'),'false')
        self.assertEqual(len(base.find('trust-anchors')),0)
        domains=root.findall('domain-config')
        self.assertEqual(len(domains),2)
        loopback = domains[1]
        self.assertEqual(loopback.get('cleartextTrafficPermitted'), 'true')
        self.assertEqual(loopback.find('domain').text, '127.0.0.1')
        self.assertEqual(loopback.find('domain').get('includeSubdomains'), 'false')
        self.assertIsNone(loopback.find('trust-anchors'))
        self.assertEqual(domains[0].find('domain').text,'bob-private-scanner.onrender.com')
        self.assertEqual(domains[0].find('domain').get('includeSubdomains'),'false')
        self.assertEqual(domains[0].find('trust-anchors/certificates').get('src'),'system')
        self.assertIn('android:networkSecurityConfig="@xml/diagnostic_network"',MANIFEST.read_text())

    def test_debug_job_cannot_claim_to_be_stable_release(self):
        workflow = DEBUG.read_text(encoding="utf-8")
        self.assertIn("ch.bob.degirocompanion.stable.voicetest", workflow)
        self.assertIn("bob-android-dev-test-not-an-update", workflow)
        self.assertNotIn("BOB_ANDROID_KEYSTORE_BASE64", workflow)
        self.assertNotIn("gh release create", workflow)
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('android.permission.INTERNET"', manifest)
        self.assertIn('android:usesCleartextTraffic="false"', manifest)
        self.assertIn('android.permission.BIND_JOB_SERVICE', manifest)
        self.assertIn('android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"', manifest)
        config = (ROOT / "android_companion/app/src/main/res/xml/product_reader.xml").read_text()
        self.assertIn('android:canPerformGestures="true"', config)
        self.assertIn('android:canTakeScreenshot="true"', config)
        self.assertIn('android:packageNames="nl.degiro.trader"', config)
        service = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/ProductReadService.kt").read_text()
        for forbidden in ['takeScreenshot(']:
            self.assertNotIn(forbidden, service)
        self.assertNotIn('event.text', service)
        self.assertIn('ProductReadRequest.attempt(SystemClock.elapsedRealtime())', service)
        self.assertIn('flagRetrieveInteractiveWindows', config)
        self.assertIn('ProductWindowPolicy.select', service)
        # One additional semantic backward scroll seeks the Top Results heading.
        # The extra action only scrolls the verified ten-row DEGIRO result list
        # back to its search header while private OCR is pending. Count changes
        # must be accompanied by explicit source/safety-contract verification.
        # One more guarded action is the single Samsung search-EditText
        # click fallback after a validated search-input gesture. The strict
        # field identity and one-shot budget are checked below.
        # The extra action is one original 10930-style BACKWARD scroll on
        # a captured, checksum-valid local Gold list while restoring search.
        # It is not a new order, click or form-field action.
        self.assertEqual(service.count('performAction('), 13)
        return_scroll = service.split('private fun returnToSearchWhileImporting(', 1)[1].split(
            'private fun deliverMorningList(', 1)[0]
        for guard in [
            'attempt>=6', 'MorningListDelivery.waiting', 'PhoneRemote.active()',
            'MorningReadRun.running', 'GoldSearchRun.running', 'isKeyguardLocked',
            'root.windowId!=expectedWindow', 'ProductScreenEvidence.PACKAGE',
            'MorningReadPolicy.listReturnScrollTarget(descriptions,backward,captured)',
            'target.refresh()', 'target.isVisibleToUser', 'rootInActiveWindow',
            'ACTION_SCROLL_BACKWARD', 'handler.postDelayed('
        ]:
            self.assertIn(guard, return_scroll)
        self.assertEqual(return_scroll.count('performAction('), 1)
        # The second Samsung tap is the missing post-capture transition:
        # only the verified Gold input, never an unfiltered catalog, card,
        # order control, PIN or guessed coordinate.
        for guard in [
            'MorningReadPolicy.postCaptureGoldSearchFocusIndex(',
            'postListCaptured=captured', 'if(keyboardVisible())return',
            'postListGestureAttempted=true',
            'ProductReadDiagnostics.Outcome.POST_LIST_SEARCH_TAP_SENT',
            'ProductReadDiagnostics.Outcome.POST_LIST_SEARCH_FOCUS_SENT',
            'if(descriptions.any { it.editable',
        ]:
            self.assertIn(guard, return_scroll)
        self.assertIn('postListCaptured: Set<String>? = null', service)
        self.assertIn('MorningListDelivery.waiting && !keyboardVisible()', service)
        self.assertIn('!MorningReadRun.running && !GoldSearchRun.running', service)
        self.assertIn('postListCaptured.all(SeriesEvidence::validIsin)', service)
        self.assertIn('postListCaptured.size in 1..10 && listImages.length() in 3..4', service)
        self.assertIn('POST_LIST_SEARCH_CONTEXT_PENDING', service)
        # A 9/10 server rejection activates only local read-only research,
        # with one owner session ticket and eight bounded rechecks of the
        # protected DEGIRO search field. No UI action on an unverified screen.
        self.assertIn('continueLocalGoldResearch(local.toList(),ticket,0,', service)
        self.assertIn('PhoneRemote.sessionId()!=ticket', service)
        self.assertIn('continueLocalGoldResearch(local,ticket,attempt+1,startedAt)', service)
        self.assertIn('continueLocalGoldResearch(local,ticket,attempt,startedAt)', service)
        self.assertIn('LocalResearchForegroundPolicy.mayWait(elapsed,', service)
        self.assertIn('LocalResearchForegroundPolicy.POLL_MS', service)
        self.assertIn('PhoneDiagnostics.queue(this)', service)
        self.assertIn('LOCAL_RESEARCH_AWAITING_DEGIRO', service)
        self.assertIn('LOCAL_RESEARCH_DEGIRO_RETURNED', service)
        self.assertIn('LOCAL_RESEARCH_DEGIRO_NOT_VISIBLE', service)
        self.assertIn('LOCAL_RESEARCH_SEARCH_UNAVAILABLE', service)
        # After the server receipt releases its own wake lock, preserve a
        # bounded non-waking screen lease ONLY for the same owner-started
        # research ticket. Broker login remains manual, no credential text
        # is observed, clicked, typed, or stored by this feature.
        bridge = service.split('private fun keepLocalResearchScreen(',1)[1].split(
            '/** One gesture then bounded semantic fallback',1)[0]
        for guard in [
            'PhoneRemote.active()', 'PhoneRemote.sessionId()!=ticket',
            'isKeyguardLocked', 'isDeviceLocked', 'power.isInteractive',
            'PowerManager.SCREEN_DIM_WAKE_LOCK',
            'LocalResearchForegroundPolicy.MAX_WAIT_MS',
            'LOCAL_RESEARCH_SCREEN_HELD'
        ]: self.assertIn(guard,bridge)
        self.assertIn('keepLocalResearchScreen(ticket)',service)
        self.assertIn('clearLocalResearchWait()\n            PhoneRemote.stop',service)
        self.assertIn('LocalResearchOwnerLoginPolicy.visible(descriptions)',service)
        self.assertIn('LOCAL_RESEARCH_OWNER_LOGIN_REQUIRED',service)
        self.assertIn('LOCAL_RESEARCH_OWNER_LOGIN_RETURNED',service)
        self.assertIn('LOCAL_RESEARCH_OWNER_LOGIN_EXPIRED',service)
        self.assertIn('localResearchAwaitingDegiro=false',service)
        self.assertIn('localResearchWaitTicket=""',service)
        self.assertIn('clearLocalResearchWait()\n            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LOCAL_RESEARCH_SEARCH_READY)',service)
        self.assertIn('ownerLoginTouchAllowed(foreground)',service)
        self.assertIn('return observation("LOCAL_RESEARCH_OWNER_LOGIN_REQUIRED")',service)
        self.assertIn('if(touchesProduct && !ownerSigningIn)',service)
        self.assertNotIn('node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)',bridge)
        auth_policy = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/LocalResearchOwnerLoginPolicy.kt").read_text()
        self.assertIn('protectedOrder',auth_policy)
        self.assertIn('labels.any(strongPin::matches)',auth_policy)
        preflight = service.split('private fun continueLocalGoldResearch(', 1)[1].split(
            'private fun returnToSearchWhileImporting(', 1)[0]
        for guard in [
            'PhoneRemote.sessionId()!=ticket', 'isDeviceLocked',
            'root?.packageName?.toString()!=ProductScreenEvidence.PACKAGE',
            'quarantinedGoldReturnScrollTarget(',
            'descriptions,backwards,local.toSet()',
            'current?.windowId==root.windowId',
            'current?.packageName?.toString()==ProductScreenEvidence.PACKAGE',
            'live[index].refresh()', 'live[index].isVisibleToUser',
            'ACTION_SCROLL_BACKWARD', 'LOCAL_RESEARCH_HEADER_SCROLL_SENT'
        ]:
            self.assertIn(guard, preflight)
        self.assertEqual(preflight.count('performAction('), 1)
        local_policy = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/MorningReadPolicy.kt").read_text()
        local_scroll = local_policy.split('fun quarantinedGoldReturnScrollTarget(',1)[1].split(
            '/** Continue only an already captured Top Results list.',1)[0]
        for guard in [
            'localCandidates.size !in 1..10', 'SeriesEvidence.validIsin',
            'genericTurboDirectory(nodes)', 'it.editable || it.containsInput',
            'marked.size !in 1..4', 'actionable.size!=1',
            'hasActualOrderOrPrivateMarker(it,form)', 'descends(it,clickableLauncher)',
            'readOnlyNodes=nodes.mapIndexed',
            'protection(readOnlyNodes)!=null', 'captureGoldList(readOnlyNodes,true)',
            'visible.kind!=Kind.COLLECT', 'visible.isins.any { it !in localCandidates }',
            'innermost(nodes,candidates).singleOrNull()'
        ]: self.assertIn(guard, local_scroll)
        # PR #1790's old Stop Loss and quantity calculations are back as
        # PURE OFFLINE simulations, not as a hidden live DEGIRO form adapter.
        offline = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/StopLossOfflineSimulation.kt").read_text()
        policy_only = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/StopLossPrefillPolicy.kt").read_text()
        manifest = (ROOT / "android_companion/app/src/main/AndroidManifest.xml").read_text()
        self.assertIn('internal object StopLossOfflineSimulation',offline)
        self.assertIn('internal object StopLossPrefillPolicy',policy_only)
        self.assertNotIn('StopLossPrefillExecutor',service)
        self.assertNotIn('StopLossPrefillSession',service)
        self.assertNotIn('StopLossPrefillActivity',manifest)
        self.assertIn('<activity android:name=".StopLossSimulationActivity" android:exported="false" />',manifest)
        self.assertIn('<activity android:name=".StopLossMockOrderActivity" android:exported="false" />',manifest)
        self.assertIn('Stop-Loss & Stückzahl üben · nur Offline-Simulation',
                      (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/ProductReadActivity.kt").read_text())
        # Source comments may identify the deliberately excluded executor,
        # but neither pure class may invoke its real broker action.
        self.assertNotIn('StopLossPrefillExecutor.execute(',offline)
        self.assertNotIn('StopLossPrefillExecutor.execute(',policy_only)
        self.assertNotIn('StopLossPrefillSession',service)
        self.assertIn('MorningReadPolicy.postCaptureGoldSearchFocusIndex(', service)
        # The research-only Gold preview may have one exact unrelated
        # global "Order platzieren" launcher. It may permit only a uniquely
        # identified search icon (or a read-only wait), never order actions.
        policy = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/MorningReadPolicy.kt").read_text()
        recovery = policy.split('private fun isolatedGoldSearchAfterLauncher(', 1)[1].split(
            '/** The independently verified read-only Gold preview', 1)[0]
        for guard in [
            'protection(nodes)!="PROTECTED_ORDER_CONFIRM"',
            'genericTurboDirectory(nodes)',
            'nodes.count { exact(it.text,"Hebelprodukte") }!=1',
            'if(!topResults && !(markets && product)) return null',
            '"orderübersicht"', '"orderzusammenfassung"',
            'productSearchWithoutLauncher(check)',
            'if(protection(clean)!=null) return null',
            'descendant(i,launcher)', 'canClick(n)',
            'Action(Kind.SEARCH,',
            'code="GOLD_GLOBAL_LAUNCHER_SEARCH"',
            'Action(Kind.WAIT,code="GOLD_SEARCH_REBUILDING")'
        ]:
            self.assertIn(guard, recovery)
        self.assertIn('isolatedGoldSearchAfterLauncher(nodes)?.let { return it }', policy)
        # This exceptional search must use the existing overlay-verified
        # bounded gesture, NEVER the ordinary direct ACTION_CLICK path.
        self.assertIn('action.code=="GOLD_GLOBAL_LAUNCHER_SEARCH"', service)
        self.assertIn('MorningReadRun.researchOnlyActive()) {', service)
        self.assertIn('val tapped=tapRecognizedSearch(root.windowId)', service)
        self.assertIn('LOCAL_RESEARCH_GLOBAL_SEARCH_TAP_REJECTED', service)
        self.assertIn('!nestedInProduct(i)', recovery)
        # The single global order-launcher label must not cause a normal
        # Gold search without a temporarily visible EditText to be classified
        # as a protected ORDER confirmation. WAIT never types any ISIN.
        preflight = service.split('private fun continueLocalGoldResearch(',1)[1].split(
            'private fun returnToSearchWhileImporting(',1)[0]
        for guard in [
            'decision.kind==MorningReadPolicy.Kind.WAIT',
            'decision.code=="GOLD_SEARCH_REBUILDING"',
            'if(goldSearchRebuilding)',
            'LocalResearchForegroundPolicy.mayWait(elapsed,',
            'continueLocalGoldResearch(local,ticket,attempt,startedAt)',
            'LOCAL_RESEARCH_GOLD_SEARCH_REBUILDING',
            'LOCAL_RESEARCH_GOLD_SEARCH_WAIT_EXPIRED'
        ]: self.assertIn(guard,preflight)
        self.assertIn('return observation("LOCAL_RESEARCH_GOLD_SEARCH_REBUILDING")',service)
        # A user-visible search result must continue through the previously
        # audited overlay/window checked text-only search gesture.
        self.assertIn('val tapped=tapRecognizedSearch(root.windowId)',service)


        seek=service.split('A fresh run can begin on yesterday',1)[1].split('val proposed=',1)[0]
        for guard in ['listImages.length()==0','MorningReadPolicy.captureGoldList(descriptions,true)',
                      'seek.kind==MorningReadPolicy.Kind.COLLECT','listTopSeekSteps>4',
                      'ACTION_SCROLL_BACKWARD','!n.isEditable','!n.isPassword']:
            self.assertIn(guard,seek)
        self.assertEqual(service.count('dispatchGesture('), 1)
        tap = service.split('private fun tapRecognizedSearch(', 1)[1].split('private fun submitSearch(', 1)[0]
        for guard in ['PhoneRemote.active()', 'ProductReadRequest.active(', 'isKeyguardLocked',
                      'MorningReadPolicy.discoverGold(descriptions)', 'MorningReadPolicy.Kind.SEARCH',
                      'SearchTapPolicy.center(', 'target.refresh()', 'refreshed!=bounds',
                      'window.layer>=app.layer', 'magnificationController.scale != 1f',
                      'isTouchExplorationEnabled', 'Display.DEFAULT_DISPLAY']:
            self.assertIn(guard, tap)
        self.assertIn('action.code=="SEARCH_NO_PROGRESS" && !searchTapAttempted', service)
        self.assertIn('searchTapAttempted=true', service)
        self.assertIn('if(category) MorningReadPolicy.Kind.CATEGORY', tap)
        self.assertIn('action.kind!=required || (input && category)', tap)
        self.assertIn('target.isEditable!=input', tap)
        self.assertIn('else if(MorningReadRun.researchOnlyActive()) MorningReadPolicy.localResearchDecision(', tap)
        self.assertIn('descriptions,MorningReadRun.target,keyboardVisible(),resultOpened=batchResultOpened)', tap)
        self.assertIn('tapRecognizedSearch(root.windowId,category=true)', service)
        # When Samsung focus alone leaves the IME closed, use only one
        # additional semantic ACTION_CLICK on the exact verified product
        # EditText. Never click an unrecognized field or trade control.
        self.assertIn('inputClickAttempted=false', service)
        self.assertIn('inputClickAttempted=true', service)
        self.assertIn('inputFocusAttempted=true', service)
        self.assertIn('!node.isVisibleToUser', service)
        self.assertIn('MorningReadPolicy.isSearchInput(', service)
        self.assertIn('node.actionList.any { it.id==AccessibilityNodeInfo.ACTION_CLICK }', service)
        self.assertIn('node.performAction(AccessibilityNodeInfo.ACTION_CLICK)', service)
        self.assertIn('SEARCH_INPUT_CLICK_SENT', service)
        self.assertIn('SEARCH_INPUT_CLICK_REJECTED', service)
        self.assertIn('keyboardVisible(),resultOpened=batchResultOpened', service)
        # Samsung Gold search may need more than four bounded category-scroll
        # actions with the keyboard previously open. Never permit a free
        # gesture or unbounded retries; all tabs remain semantically verified.
        self.assertIn('++categorySteps>7', service)
        # The screenshot-confirmed 278k Turbos is unfiltered. Detect its
        # identity BEFORE generic search retries and without a 10-second
        # timeout that can miss a slow WebView transition.
        # DEGIRO's visible all-results CTA demonstrably opens the
        # UNFILTERED global Turbos directory. Do not execute it at all from
        # the owner-started native Gold reader; keep local preview capture
        # and the server's ten-original-rows import gate unchanged.
        self.assertIn('MorningReadPolicy.preferGoldPreviewRead(descriptions)', service)
        self.assertIn('LIST_GOLD_PREVIEW_DIRECT', service)
        self.assertNotIn('tapRecognizedSearch(root.windowId,allResults=true)', service)
        self.assertIn('MorningReadPolicy.genericTurboRecovery(descriptions,', service)
        self.assertIn('listGoldPreviewConfirmed=true', service)
        self.assertIn('listGoldPreviewConfirmed=false', service)
        self.assertNotIn('age in 0..10000L', service)
        self.assertIn('LIST_GENERIC_TURBO_RETURN_STUCK', service)
        self.assertIn('LIST_GENERIC_TURBO_START_BACK_SENT', service)
        self.assertIn('!ProductReadRequest.active(SystemClock.elapsedRealtime())', service)
        self.assertIn('MorningReadPolicy.goldNeedsKeyboardDismissal(', service)
        # All full-list starts must use the SAME lease, instead of
        # silently reverting to 60 s from the one-button activity.
        self.assertIn('ProductReadRequest.startGoldList(now)', service)
        delivery = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/MorningListDelivery.kt").read_text()
        run = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/MorningReadRun.kt").read_text()
        transfer = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/MorningReadTransfer.kt").read_text()
        # A rejected batch can trigger local read-only research, but never
        # promote these unconfirmed candidate identities or quotes into
        # the authenticated daily list or any trading decision.
        self.assertIn('MorningListDelivery.onProvisionalResearch=', service)
        self.assertIn('MorningReadRun.beginDiscovered(this,local,researchOnly=true)', service)
        self.assertIn('remove("localCandidates")', delivery)
        self.assertIn('ProvisionalIsinReadPolicy.candidates(', delivery)
        self.assertIn('if(researchOnly) "unverified-local-gold-preview"', run)
        self.assertIn('if(originalListAt==null && !researchOnly)', run)
        self.assertIn('if(data.optBoolean("researchOnly",false))return false', transfer)
        phone = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/PhoneRemote.kt").read_text()
        self.assertIn('MorningReadRun.researchOnlyActive()) empty("LOCAL_RESEARCH_ACTIVE")', phone)
        self.assertIn('!MorningReadRun.researchOnlyActive()', phone)
        self.assertIn('check(!org.json.JSONObject(raw).optBoolean("researchOnly",false))', transfer)
        request=(ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/ProductReadRequest.kt").read_text()
        activity=(ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/ProductReadActivity.kt").read_text()
        self.assertIn('fun startGoldList(now: Long) = start(now,120000L,60)', request)
        self.assertIn('private fun startAutomaticTest()', activity)
        self.assertIn('private fun startPreparedGoal(query: String)', activity)
        self.assertIn('ProductReadRequest.startGoldList(SystemClock.elapsedRealtime())', activity)
        self.assertIn('if(existingDetails) ProductReadRequest.start(SystemClock.elapsedRealtime())', activity)
        self.assertIn('else ProductReadRequest.startGoldList(SystemClock.elapsedRealtime())', activity)
        self.assertIn('else ProductReadRequest.start(now)', service)
        self.assertIn('GoldSearchRun.searchOnlyQuery==null', service)
        self.assertIn('!GoldSearchRun.openingProduct', service)
        submit = service.split('private fun submitSearch(', 1)[1].split('private fun scrollCategories(', 1)[0]
        self.assertIn('android.os.Build.VERSION.SDK_INT>=30', submit)
        self.assertIn('node.isEditable && node.isFocused', submit)
        self.assertIn('node.actionList.any { it.id==AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id }', submit)
        self.assertEqual(submit.count('performAction('), 1)
        self.assertIn('node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)', submit)
        single_page = service[:service.index('private fun navigationTree(')]
        self.assertNotIn('ACTION_CLICK', single_page)
        self.assertNotIn('ACTION_SET_TEXT', single_page)
        self.assertIn('MorningReadPolicy.detailDecision(descriptions,MorningReadRun.target,MorningReadRun.importedListRun(),keyboardVisible())', service)
        self.assertIn('if (!MorningReadRun.reading && navigateMorning(root))', service)
        fresh = service.split('private fun productRoot(', 1)[1].split('private fun readOnce(', 1)[0]
        for guard in ['record && MorningReadRun.importedListRun() && !MorningReadRun.reading',
                      'android.os.Build.VERSION.SDK_INT>=33', 'clearCache()', 'if(!refreshed)return null']:
            self.assertIn(guard, fresh)
        self.assertLess(fresh.index('clearCache()'), fresh.index('val direct = rootInActiveWindow'))

        self.assertIn('ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,if(gold) GoldSearchRun.query else MorningReadRun.target', service)
        search_run = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/GoldSearchRun.kt").read_text()
        self.assertIn('require(DegiroGoal.acceptsQuery(query))', search_run)
        goals = (ROOT / "android_companion/app/src/main/java/ch/bob/degirocompanion/DegiroGoal.kt").read_text()
        self.assertIn('query in setOf("Gold", "Silber") || SeriesEvidence.validIsin(query)', goals)
        self.assertIn('val query get() = searchOnlyQuery ?: "Gold"', search_run)
        self.assertIn('MorningReadPolicy.discoverGold(descriptions)', service)
        self.assertIn('flagIncludeNotImportantViews', config)
        self.assertIn('performGlobalAction(GLOBAL_ACTION_BACK)', service)
        self.assertIn('AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD', service)
        self.assertIn('root.packageName?.toString() != ProductScreenEvidence.PACKAGE', service)

    def test_no_private_key_material_is_tracked_in_android_setup(self):
        ignore = (ROOT / "android_companion/.gitignore").read_text(encoding="utf-8")
        self.assertIn("**/*.p12", ignore)
        self.assertIn("**/*.jks", ignore)
        script = (ROOT / "android_companion/tools/setup_stable_signing.sh").read_text(encoding="utf-8")
        self.assertIn("gh secret set", script)
        self.assertIn("gh variable set", script)
        self.assertIn("gh auth status", script)
        self.assertNotIn("git add", script)
        self.assertIn('gh variable list -R "$repo" --json name,value', script)
        self.assertIn('Signing identity conflict', script)
        # Shell syntax is checked without running key creation or GitHub writes.
        subprocess.run(["bash", "-n",
                        str(ROOT / "android_companion/tools/setup_stable_signing.sh")],
                       check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
