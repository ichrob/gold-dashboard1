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

/** Local stable-app UI only. Never starts DEGIRO or asks for credentials. */
@RunWith(AndroidJUnit4::class)
class DegiroReadOnlyDeviceTest {
    @Test fun showsPermissionBlockAndExplicitStopWithoutReader() {
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        context.startActivity(Intent(context,DegiroReadOnlyActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        val device=UiDevice.getInstance(instrumentation)
        assertNotNull(device.wait(Until.findObject(
            By.text("BOB HANDY · DEGIRO NUR LESEN")),10_000))
        assertNotNull(device.wait(Until.findObject(
            By.text("DEGIRO nur lesen · 45 Sekunden · keine Order")),5_000))
        val stop=device.findObject(By.text("STOPP · Nur-Lesen-Prüfung beenden"))
        assertNotNull(stop)
        stop.click()
        assertNotNull(device.wait(Until.findObject(
            By.textContains("Keine Order oder Freigabe zum Handel")),5_000))
    }
}
