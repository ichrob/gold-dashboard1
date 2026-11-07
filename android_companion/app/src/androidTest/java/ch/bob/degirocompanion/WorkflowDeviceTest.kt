package ch.bob.degirocompanion

import android.app.UiAutomation
import android.content.Intent
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Executes the real AccessibilityService against a separate offline Android app. */
@RunWith(AndroidJUnit4::class)
class WorkflowDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private val automation get() = instrumentation.getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES)
    private val app = "org.bob.workflowfixture"
    private val goal = "Schreibe Gold in das Suchfeld"
    private fun shell(command: String) {
        android.os.ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command)).use { it.readBytes() }
    }
    private fun main(block: () -> Unit) = instrumentation.runOnMainSync(block)
    private fun await(message: String, predicate: () -> Boolean) {
        val until = SystemClock.elapsedRealtime() + 30_000
        while (SystemClock.elapsedRealtime() < until) {
            var result = false
            main { result = predicate() }
            if (result) return
            SystemClock.sleep(100)
        }
        fail(message + ": " + context.getSharedPreferences("workflow_selftest",0).getString("detail", "") + " / " + WorkflowService.message + " [fixture OCR: " + WorkflowService.screenshotText + "]")
    }
    @Before fun setup() {
        context.getSharedPreferences("local_workflows_v1",0).edit().clear().commit()
        shell("settings put secure enabled_accessibility_services " + context.packageName + "/ch.bob.degirocompanion.WorkflowService")
        shell("settings put secure accessibility_enabled 1")
        await("Service did not connect") { WorkflowService.instance != null }
    }
    @After fun cleanup() {
        main { WorkflowService.stop() }
        shell("am force-stop " + app)
        shell("settings delete secure enabled_accessibility_services")
        await("Service did not disconnect") { WorkflowService.instance == null }
    }
    private fun launch(mode: String) {
        shell("am force-stop " + app)
        main { assertTrue(WorkflowService.instance!!.beginAutomatic(app,goal,false)) }
        context.startActivity(Intent().setClassName(app,app + ".MainActivity").putExtra("mode",mode)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
    }
    private fun verified() {
        await("Real screen result was not verified") { WorkflowService.run?.let { WorkflowAiPolicy.verified(it) } == true }
        assertNotNull(WorkflowLibrary.match(context,app,goal))
        val root = automation.rootInActiveWindow
        assertNotNull(root)
        val field = root.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
        assertEquals("Gold",field.text.toString())
        assertEquals("SUCCEEDED",WorkflowHealth.diagnostic(context)!!.getString("state"))
    }
    @Test fun opensSearchWritesChecksAndAdaptsSavedWorkflowToAlreadyOpenField() {
        launch("closed")
        verified()
        assertEquals(2,WorkflowService.run!!.index)
        launch("open")
        verified()
        assertEquals(1,WorkflowService.run!!.index)
    }
    @Test fun ownerSequenceOpensFutureFieldAndWritesLettersAndDecimalNumber() {
        val sequence = listOf(
            WorkflowComposer.command(WorkflowAction.CLICK, "Suche", expected="Suchfeld")!!,
            WorkflowComposer.command(WorkflowAction.WRITE, "Suchfeld", "Silber 123,45")!!,
            WorkflowComposer.command(WorkflowAction.WAIT, "Silber 123,45")!!).joinToString("\n")
        main { assertTrue(WorkflowService.instance!!.beginAutomatic(app, sequence, false)) }
        context.startActivity(Intent().setClassName(app, app + ".MainActivity").putExtra("mode", "closed")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Sequence did not verify every step") { WorkflowService.run?.let { WorkflowAiPolicy.verified(it) } == true }
        assertEquals(3, WorkflowService.run!!.index)
        val field = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
        assertEquals("Silber 123,45", field.text.toString())
    }
    @Test fun ambiguousOrProtectedFieldsNeverWriteOrCacheSuccess() {
        for (mode in listOf("ambiguous","protected")) {
            launch(mode)
            await("Unsafe screen did not stop") { WorkflowHealth.diagnostic(context)?.optString("state") == "STOPPED" }
            assertNull(WorkflowLibrary.match(context,app,goal))
            val root = automation.rootInActiveWindow
            val fields = root.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text")
            assertEquals(1,fields.size)
            assertTrue(fields.all { it.isShowingHintText || it.text.isNullOrBlank() })
            assertEquals(0,WorkflowHealth.diagnostic(context)!!.getInt("confirmed"))
        }
    }
    @Test fun screenshotTextIsReadLocallyWithoutStartingActions() {
        main { assertTrue(WorkflowService.instance!!.begin(app,null,screenshot=true)) }
        context.startActivity(Intent().setClassName(app,app + ".MainActivity").putExtra("mode","ocr")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Screenshot OCR did not read fixture") { WorkflowService.screenshotText.contains("314159") }
        assertNull(WorkflowService.run)
        assertNull(WorkflowLibrary.match(context,app,goal))
    }
    @Test fun degiroGoalHandsOffToReaderWithoutStartingGenericActions() {
        context.getSharedPreferences("workflow_auto_v1",0).edit()
            .putString("lastApp",WorkflowAppRoute.DEGIRO).putString("lastGoal","Gold").commit()
        context.startActivity(Intent(context,WorkflowActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Workflow screen did not open") {
            automation.rootInActiveWindow?.findAccessibilityNodeInfosByText("START · Bob erledigt den Auftrag")?.isNotEmpty() == true
        }
        val start = automation.rootInActiveWindow.findAccessibilityNodeInfosByText("START · Bob erledigt den Auftrag").single()
        assertTrue(start.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
        await("DEGIRO reader handoff missing") {
            automation.rootInActiveWindow?.findAccessibilityNodeInfosByText("DEGIRO lesen · Produkt und Morgenliste")?.isNotEmpty() == true
        }
        assertFalse(GoldSearchRun.running) // Fixture device has no enabled product reader.
        assertNull(WorkflowService.run)
        assertTrue(automation.rootInActiveWindow.findAccessibilityNodeInfosByText("Lesedienst zuerst einschalten.").isNotEmpty())
        context.getSharedPreferences("workflow_auto_v1",0).edit().clear().commit()
    }
    @Test fun builtInSelfTestChecksClickWriteAndScreenshot() {
        context.getSharedPreferences("workflow_selftest",0).edit().clear().commit()
        context.startActivity(Intent(context,WorkflowSelfTestActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Built-in self-test failed") {
            context.getSharedPreferences("workflow_selftest",0).getBoolean("success",false)
        }
        assertEquals(3,WorkflowHealth.diagnostic(context)!!.getInt("confirmed"))
        assertFalse(LocalWorkflow.allowedApp(context.packageName))
        main { assertFalse(WorkflowService.instance!!.begin(context.packageName,null)) }
    }
    @Test fun stopBeforeAppLaunchInvalidatesPendingAutomation() {
        main {
            assertTrue(WorkflowService.instance!!.beginAutomatic(app,goal,false))
            WorkflowService.stop()
        }
        context.startActivity(Intent().setClassName(app,app + ".MainActivity").putExtra("mode","open").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        SystemClock.sleep(2000)
        assertNull(WorkflowService.run)
        assertNull(WorkflowLibrary.match(context,app,goal))
        assertEquals("STOPPED",WorkflowHealth.diagnostic(context)!!.getString("state"))
    }
}
