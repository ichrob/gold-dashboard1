package ch.bob.degirocompanion

import android.content.Intent
import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** UI-only acceptance precursor. Does not press approval, navigate to Bob or trade. */
@RunWith(AndroidJUnit4::class)
class BobHandyDeepLinkUiTest {
    @Test fun untrustedLinkCreatesPreviewButDoesNotLaunchAnything() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val context = inst.targetContext
        val device = UiDevice.getInstance(inst)
        val proposed = Intent(Intent.ACTION_VIEW,
            Uri.parse("bobhandy://handoff/OPEN_PRODUCTS")).apply {
            setClassName(context.packageName, "ch.bob.degirocompanion.MainActivity")
            addCategory(Intent.CATEGORY_BROWSABLE)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        context.startActivity(proposed)
        assertNotNull(device.wait(Until.findObject(
            By.textContains("Per Link/Android-Teilen vorgeschlagen: Goldprodukte anzeigen")), 5000))
        assertTrue(device.currentPackageName == context.packageName)
    }
}
