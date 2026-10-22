package ch.bob.degirocompanion

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * This instrumentation test uses only our OWN test Activity. It verifies
 * the preselected "Bob öffnen" label is real text, not a hint, and preview never executes.
 */
@RunWith(AndroidJUnit4::class)
class PhoneTaskUiTest {
    @Test fun harmlessDefaultIsPrepopulatedAndNotAutoExecuted() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val pkg = context.packageName
        val launch = context.packageManager.getLaunchIntentForPackage(pkg)
        assertNotNull(launch)
        context.startActivity(launch!!.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))

        val field = device.wait(Until.findObject(By.desc("Bob Handy-Auftrag")), 5_000)
        assertNotNull(field)
        assertEquals("Bob öffnen", field.text)

        val previewButton = device.findObject(By.text("Handy-Auftrag prüfen"))
        assertNotNull(previewButton)
        previewButton.click()
        val preview = device.wait(
            Until.findObject(By.textContains("Prüfung OK: Bob im Browser öffnen")), 5_000
        )
        assertNotNull(preview)
        // Preview MUST leave us in the lab, before the second explicit tap.
        assertTrue(device.currentPackageName == pkg)
    }
}
