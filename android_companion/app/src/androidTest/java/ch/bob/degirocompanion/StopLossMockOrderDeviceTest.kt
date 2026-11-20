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

/** Local Android View-tree integration. NO broker package, account or order. */
@RunWith(AndroidJUnit4::class)
class StopLossMockOrderDeviceTest {
    private val instrumentation=InstrumentationRegistry.getInstrumentation()
    private val device=UiDevice.getInstance(instrumentation)
    private val context=instrumentation.targetContext

    private fun exercise(case:String, expected:String) {
        val launch=Intent(context,StopLossMockOrderActivity::class.java)
            .putExtra("mock_scenario",case)
            .putExtra("mock_isin","DE000PM96QY2")
            .putExtra("mock_quantity",7)
            .putExtra("mock_stop_cents",1243L)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        context.startActivity(launch)
        val start=device.wait(Until.findObject(By.text("Testoberfläche automatisch bedienen")),10_000)
        assertNotNull("Synthetic form start missing",start)
        start.click()
        val result=device.wait(Until.findObject(By.textContains("TEST BESTANDEN")),15_000)
        assertNotNull("Synthetic form failed to reach expected safe result",result)
        if(expected.isNotBlank()) {
            val body=device.wait(Until.findObject(By.textContains(expected)),5_000)
            assertNotNull("Expected stop/field output not found: $expected",body)
        }
        assertTrue(result.text.contains("0 Brokerzugriffe"))
        assertTrue(result.text.contains("0 Orders"))
    }
    @Test fun writesAndVerifiesCalculatedModelValuesOnActualMockViews() {
        exercise("HAPPY_PATH","12,43")
    }
    @Test fun wrongIsinIsBlockedBeforeAnyMockWrite() {
        exercise("WRONG_ISIN","PRODUKT_ISIN_NICHT_ERKANNT")
    }
    @Test fun aMockBuyFormNeverPassesSellVerification() {
        exercise("BUY_SELECTED","VERKAUF_NICHT_BESTAETIGT")
    }
    @Test fun ambiguousRealMockViewCaptionsBlockWriting() {
        exercise("AMBIGUOUS_STOP_FIELD","STOP_FELD_NICHT_EINDEUTIG")
    }
}
