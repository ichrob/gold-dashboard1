"""Static regression: stable Android signing/update policy never backslides.

No secrets, keystores, builds, browser or device access is needed for this test.
"""
import unittest
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
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn('conclusion', workflow)
        self.assertIn('grep -Fxq "$GITHUB_SHA"', workflow)
        self.assertIn('BOB_ANDROID_KEYSTORE_BASE64', workflow)
        self.assertIn('BOB_ANDROID_STORE_PASSWORD', workflow)
        self.assertIn('BOB_ANDROID_KEY_PASSWORD', workflow)
        self.assertIn('BOB_ANDROID_CERT_SHA256', workflow)
        self.assertIn('apksigner', workflow)
        self.assertIn('if [ "$actual" != "$expected" ]', workflow)
        self.assertIn("ch.bob.degirocompanion.stable", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("rm -f", workflow)
        self.assertNotIn("pull_request:", workflow)

    def test_debug_job_cannot_claim_to_be_stable_release(self):
        workflow = DEBUG.read_text(encoding="utf-8")
        self.assertIn("ch.bob.degirocompanion.stable.voicetest", workflow)
        self.assertNotIn("BOB_ANDROID_KEYSTORE_BASE64", workflow)
        self.assertNotIn("gh release create", workflow)
        manifest = MANIFEST.read_text(encoding="utf-8")
        self.assertIn('android.permission.INTERNET" tools:node="remove"', manifest)
        self.assertNotIn('BIND_ACCESSIBILITY_SERVICE', manifest)

    def test_no_private_key_material_is_tracked_in_android_setup(self):
        ignore = (ROOT / "android_companion/.gitignore").read_text(encoding="utf-8")
        self.assertIn("**/*.p12", ignore)
        self.assertIn("**/*.jks", ignore)
        script = (ROOT / "android_companion/tools/setup_stable_signing.sh").read_text(encoding="utf-8")
        self.assertIn("gh secret set", script)
        self.assertIn("gh variable set", script)
        self.assertIn("gh auth status", script)
        self.assertNotIn("git add", script)


if __name__ == "__main__":
    unittest.main()
