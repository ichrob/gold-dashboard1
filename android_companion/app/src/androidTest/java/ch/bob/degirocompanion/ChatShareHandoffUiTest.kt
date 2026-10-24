package ch.bob.degirocompanion

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Local UI safety check; this test never taps launch and never opens DEGIRO.
 * The CI assembles this APK, real Samsung acceptance is a separate step.
 */
@RunWith(AndroidJUnit4::class)
class ChatShareHandoffUiTest {
    @Test fun shareShowsPreviewButNeverLaunchesBrowserByItself() {
        val inst = InstrumentationRegistry.getInstrumentation()
        val context = inst.targetContext
        val device = UiDevice.getInstance(inst)
        val intent = Intent(Intent.ACTION_SEND).apply {
            setClassName(context.packageName, "ch.bob.degirocompanion.MainActivity")
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, ChatShareHandoff.PRODUCTS)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        context.startActivity(intent)
        val expected = device.wait(
            Until.findObject(By.textContains("Aus ChatGPT/Android-Teilen vorgeschlagen: Goldprodukte anzeigen")),
            5_000
        )
        assertNotNull(expected)
        assertTrue(device.currentPackageName == context.packageName)
    }
}
