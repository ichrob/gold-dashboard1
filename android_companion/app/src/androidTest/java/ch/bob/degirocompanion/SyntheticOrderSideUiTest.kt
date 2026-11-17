package ch.bob.degirocompanion

import android.content.Intent
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Click both sides on our synthetic screen only; never launch the broker. */
@RunWith(AndroidJUnit4::class)
class SyntheticOrderSideUiTest {
    @Test fun tappingBuyAndSellOpensOnlyLocalDemoForms() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val device = UiDevice.getInstance(instrumentation)
        context.startActivity(Intent(context, SyntheticOrderSideActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))

        assertNotNull(device.wait(Until.findObject(By.text("DEMO: KAUF")), 5_000))
        assertNotNull(device.findObject(By.text("DEMO: VERKAUF")))
        device.findObject(By.text("DEMO: KAUF")).click()
        val buy = device.wait(Until.findObject(
            By.text("DEMO: KAUF-ORDERMASKE – KEIN ECHTER HANDEL")), 5_000)
        assertNotNull(buy)

        device.findObject(By.text("DEMO: VERKAUF")).click()
        val sell = device.wait(Until.findObject(
            By.text("DEMO: VERKAUF-ORDERMASKE – KEIN ECHTER HANDEL")), 5_000)
        assertNotNull(sell)
        assertNotNull(device.findObject(By.textContains("KEIN ORDER-VERSAND")))
        assertNull("There must be no real submission control",
            device.findObject(By.text("Order platzieren")))
        assertTrue("The foreground is still the Bob app, not DEGIRO",
            device.currentPackageName.startsWith("ch.bob.degirocompanion"))
    }
}
