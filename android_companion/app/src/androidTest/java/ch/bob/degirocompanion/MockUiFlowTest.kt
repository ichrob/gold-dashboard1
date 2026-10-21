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
 * Verifies screen search, simulated text input, tap, and readable result
 * on our OWN synthetic UI only. Never opens or controls the DEGIRO app.
 */
@RunWith(AndroidJUnit4::class)
class MockUiFlowTest {
    @Test fun simulatedTouchAndEntryNeverTrade() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        val pkg = context.packageName
        val launch = context.packageManager.getLaunchIntentForPackage(pkg)
        assertNotNull(launch)
        context.startActivity(launch!!.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        val field = device.wait(Until.findObject(By.desc("Mock ISIN Eingabe")), 5_000)
        assertNotNull(field)
        field.setText("DE000FG14AV8")
        val search = device.findObject(By.text("DEMO: Produkt suchen"))
        assertNotNull(search)
        search.click()
        val found = device.wait(Until.findObject(By.textContains("DEMO-TREFFER: DE000FG14AV8")), 5_000)
        assertNotNull(found)
        assertTrue(found.text.contains("KEIN ECHTER HANDEL"))
    }
}
