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
        self.assertEqual(len(domains),1)
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
        self.assertEqual(service.count('performAction('), 11)
        return_scroll = service.split('private fun returnToSearchWhileImporting(', 1)[1].split(
            'private fun deliverMorningList(', 1)[0]
        for guard in [
            'attempt>=4', 'MorningListDelivery.waiting', 'PhoneRemote.active()',
            'MorningReadRun.running', 'GoldSearchRun.running', 'isKeyguardLocked',
            'root.windowId!=expectedWindow', 'ProductScreenEvidence.PACKAGE',
            'MorningReadPolicy.listReturnScrollTarget(descriptions,backward,captured)',
            'target.refresh()', 'target.isVisibleToUser', 'rootInActiveWindow',
            'ACTION_SCROLL_BACKWARD', 'handler.postDelayed('
        ]:
            self.assertIn(guard, return_scroll)
        self.assertEqual(return_scroll.count('performAction('), 1)

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
        self.assertIn('tapRecognizedSearch(root.windowId,category=true)', service)
        self.assertIn('++categorySteps>4', service)
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

        self.assertIn('ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,if(gold) "Gold" else MorningReadRun.target', service)
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
