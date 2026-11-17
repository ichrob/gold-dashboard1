package ch.bob.degirocompanion

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Confirms local, non-exported, read-only UI. No broker installed or contacted. */
@RunWith(AndroidJUnit4::class)
class StopLossReadOnlyDeviceTest {
    @Test fun localProbeExplainsBoundariesAndCanStopWithoutBroker() {
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        val device=UiDevice.getInstance(instrumentation)
        context.startActivity(Intent(context,StopLossReadOnlyActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        assertNotNull(device.wait(Until.findObject(
            By.text("BOB · DEGIRO-MASKE NUR ERKENNEN")),10_000))
        assertNotNull(device.wait(Until.findObject(
            By.textContains("er tippt keine Felder an")),5_000))
        assertNotNull(device.findObject(By.text("DEGIRO jetzt nur lesen · 45 Sekunden")))
        val stop=device.findObject(By.text("STOPP · Prüfung beenden"))
        assertNotNull(stop)
        stop.click()
        assertNotNull(device.wait(Until.findObject(
            By.textContains("keine Handelserlaubnis")),5_000))
    }
}
