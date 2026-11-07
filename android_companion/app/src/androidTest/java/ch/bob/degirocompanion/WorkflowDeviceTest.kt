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
    @Test fun screenshotAndTextMessageRunsThroughComposer() {
        context.getSharedPreferences("workflow_auto_v1", 0).edit().putString("lastApp", app).commit()
        val image = android.graphics.Bitmap.createBitmap(900, 300, android.graphics.Bitmap.Config.ARGB_8888)
        val canvas = android.graphics.Canvas(image)
        canvas.drawColor(android.graphics.Color.WHITE)
        canvas.drawText("Suche", 40f, 160f, android.graphics.Paint().apply {
            color = android.graphics.Color.BLACK; textSize = 90f; isAntiAlias = true
        })
        val file = java.io.File(context.cacheDir, "composer-fixture.png")
        file.outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        image.recycle()
        val activity = instrumentation.startActivitySync(Intent(context, WorkflowActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as WorkflowActivity
        fun field(name: String): Any? = WorkflowActivity::class.java.getDeclaredField(name).apply { isAccessible = true }.get(activity)
        try {
            main {
                (field("goal") as android.widget.EditText).setText("Tippe auf Suche und warte auf Suchfeld\nSchreibe Silber 123,45 in Suchfeld")
                WorkflowActivity::class.java.getDeclaredMethod("readImage", android.net.Uri::class.java, Boolean::class.javaPrimitiveType)
                    .apply { isAccessible = true }.invoke(activity, android.net.Uri.fromFile(file), true)
            }
            await("Attached screenshot was not read locally") { (field("attachmentLabels") as List<*>).contains("Suche") }
            main {
                fun send(view: android.view.View): android.widget.Button? {
                    if (view is android.widget.Button && view.text.toString() == "Senden") return view
                    if (view is android.view.ViewGroup) for (i in 0 until view.childCount) send(view.getChildAt(i))?.let { return it }
                    return null
                }
                assertTrue(send(activity.window.decorView)!!.performClick())
            }
            await("Screenshot/text request did not complete") { WorkflowService.run?.let { WorkflowAiPolicy.verified(it) } == true }
            val fieldNode = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
            assertEquals("Silber 123,45", fieldNode.text.toString())
        } finally {
            main { activity.finish() }; file.delete()
        }
    }
    @Test fun learnsUnlabelledSymbolRecognizesMovedIconAndStopsOnDuplicates() {
        context.getSharedPreferences("workflow_symbols_v1",0).edit().clear().commit()
        context.startActivity(Intent().setClassName(app, app + ".MainActivity").putExtra("mode", "symbol")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Unlabelled icon missing") { automation.rootInActiveWindow?.findAccessibilityNodeInfosByViewId(app + ":id/symbol_button")?.size == 1 }
        SystemClock.sleep(700)
        val node = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/symbol_button").single()
        val bounds = android.graphics.Rect(); node.getBoundsInScreen(bounds)
        assertTrue(node.text.isNullOrBlank()); assertTrue(node.contentDescription.isNullOrBlank())
        val screenshot = automation.takeScreenshot()!!
        val pattern = WorkflowSymbolMatch.pattern(WorkflowSymbols.gray(screenshot), screenshot.width, screenshot.height,
            SymbolBox(bounds.left, bounds.top, bounds.right, bounds.bottom))!!
        screenshot.recycle()
        assertTrue(WorkflowSymbols.save(context, app, LearnedSymbol("Lupe", "Suchfeld", pattern)))
        assertNull(WorkflowSymbols.plan(context, "org.other.app", "Öffne Lupe"))
        assertEquals(0L, WorkflowSymbols.list(context,app).single().verifiedAt)
        fun start(mode: String) {
            shell("am force-stop " + app)
            main { assertTrue(WorkflowService.instance!!.beginAutomatic(app,"Öffne Lupe",false)) }
            context.startActivity(Intent().setClassName(app, app + ".MainActivity").putExtra("mode",mode)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        }
        start("symbol-moved")
        await("Learned moved icon did not open search") { WorkflowService.run?.let { WorkflowAiPolicy.verified(it) } == true }
        assertTrue(WorkflowSymbols.list(context, app).single().verifiedAt > 0)
        assertEquals(1, automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").size)
        start("symbol-duplicate")
        await("Duplicate icons did not stop") { WorkflowService.run?.finished == true }
        assertEquals(0, WorkflowService.run!!.index)
        assertEquals(0, automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").size)
        assertTrue(WorkflowSymbols.forget(context, app, "Lupe"))
        assertNull(WorkflowSymbols.plan(context, app, "Öffne Lupe"))
    }
    @Test fun demonstrationCreatesReviewableDraftWithoutExecutingAndCanBeReplayed() {
        context.getSharedPreferences("workflow_result_v1",0).edit().clear().commit()
        main { assertTrue(WorkflowService.instance!!.beginDemonstration(app)) }
        context.startActivity(Intent().setClassName(app,app + ".MainActivity").putExtra("mode","closed")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Demonstration did not observe fixture") { WorkflowService.observation?.app == app }
        assertNull(WorkflowService.run)
        val button = automation.rootInActiveWindow.findAccessibilityNodeInfosByText("Suche").single()
        val buttonSensitive = if (android.os.Build.VERSION.SDK_INT >= 34) button.isAccessibilityDataSensitive else false
        val buttonBounds = android.graphics.Rect(); button.getBoundsInScreen(buttonBounds)
        shell("input tap ${buttonBounds.centerX()} ${buttonBounds.centerY()}")
        await("Search field not observed") { WorkflowService.observation?.nodes?.any { it.editable } == true }
        val field = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
        val fieldSensitive = if (android.os.Build.VERSION.SDK_INT >= 34) field.isAccessibilityDataSensitive else false
        val fieldBounds = android.graphics.Rect(); field.getBoundsInScreen(fieldBounds)
        shell("input tap ${fieldBounds.centerX()} ${fieldBounds.centerY()}")
        shell("input text Gold")
        SystemClock.sleep(700)
        main { WorkflowService.endDemonstration() }
        assertNull(WorkflowService.run)
        val draft = WorkflowService.demonstrationDraft!!.second
        assertEquals("Events=${WorkflowService.demonstrationEvents}/${WorkflowService.demonstrationAllEvents}; sensitive=$buttonSensitive/$fieldSensitive; mask=${WorkflowService.instance!!.serviceInfo.eventTypes}; check=${WorkflowService.demonstrationCheck}; state=${WorkflowService.message}",2,draft.size); assertEquals("Gold",draft.last().value)
        assertNull(WorkflowResultStore.previous(context,app))
        // The owner reviews the click result before replaying the draft.
        val reviewed = draft.map { if (it.action == WorkflowAction.CLICK) it.copy(expected="Suchfeld") else it }
        shell("am force-stop " + app)
        main { assertTrue(WorkflowService.instance!!.begin(app,reviewed)) }
        context.startActivity(Intent().setClassName(app,app + ".MainActivity").putExtra("mode","closed")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Reviewed demonstration did not replay") { WorkflowService.run?.let { WorkflowAiPolicy.verified(it) } == true }
        assertTrue(WorkflowResultStore.summary(context).startsWith("Erledigt"))
        val changed = WorkflowRevision.apply("Nimm Silber statt Gold",WorkflowResultStore.previous(context,app)!!)!!
        assertEquals("Silber",changed.last().value)
        assertNull(WorkflowResultStore.previous(context,"org.other.app"))
        WorkflowService.demonstrationDraft = null
    }
    @Test fun cropZoomPreservesImageSelectionAndAllowsCorrection() {
        val activity = instrumentation.startActivitySync(Intent(context,WorkflowActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as WorkflowActivity
        val bitmap = android.graphics.Bitmap.createBitmap(400,400,android.graphics.Bitmap.Config.ARGB_8888)
        try {
            main {
                val crop = WorkflowSymbolCrop(activity,bitmap)
                val parent = android.widget.FrameLayout(activity); parent.addView(crop)
                crop.layout(0,0,400,400)
                fun touch(action: Int,x: Float,y: Float) {
                    val event = android.view.MotionEvent.obtain(0,1,action,x,y,0)
                    crop.onTouchEvent(event); event.recycle()
                }
                touch(android.view.MotionEvent.ACTION_DOWN,80f,80f); touch(android.view.MotionEvent.ACTION_UP,220f,220f)
                val before = crop.box()!!; crop.zoomBy(2f); assertEquals(before,crop.box())
                crop.zoomBy(.5f)
                touch(android.view.MotionEvent.ACTION_DOWN,80f,80f); touch(android.view.MotionEvent.ACTION_UP,60f,60f)
                assertEquals(60,crop.box()!!.left); assertEquals(220,crop.box()!!.right)
                crop.resetSelection(); assertNull(crop.box())
            }
        } finally { main { activity.finish() }; bitmap.recycle() }
    }
    @Test fun simplifiedHomeKeepsStopVisibleAndSupportsHistoryChanges() {
        context.getSharedPreferences("workflow_result_v1",0).edit().clear().commit()
        context.getSharedPreferences("workflow_auto_v1",0).edit().putString("lastApp",app).commit()
        launch("closed"); verified()
        val activity = instrumentation.startActivitySync(Intent(context,WorkflowActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as WorkflowActivity
        fun find(view: android.view.View, text: String): android.widget.Button? {
            if (view is android.widget.Button && view.text.toString() == text) return view
            if (view is android.view.ViewGroup) for (i in 0 until view.childCount) find(view.getChildAt(i),text)?.let { return it }
            return null
        }
        fun field(name: String): Any? = WorkflowActivity::class.java.getDeclaredField(name).apply { isAccessible = true }.get(activity)
        try {
            main {
                val root = activity.window.decorView
                assertTrue((field("appLabel") as android.widget.TextView).text.contains("Workflow fixture"))
                assertNotNull(find(root,"Senden")); assertNotNull(find(root,"STOPP"))
                assertNull(find(root,"Kostenlosen KI-Zugang prüfen")); assertNull(find(root,"Auftragsfolge starten"))
                assertNotNull(find(root,"Wiederholen")); assertNotNull(find(root,"Ändern"))
                find(root,"Ändern")!!.performClick()
                val input = field("goal") as android.widget.EditText
                assertEquals(goal,input.text.toString())
                input.setText("Nimm Silber statt Gold")
            }
            SystemClock.sleep(500)
            main {
                val rect = android.graphics.Rect()
                assertTrue(find(activity.window.decorView,"STOPP")!!.getGlobalVisibleRect(rect))
                assertTrue(rect.height() > 0)
                find(activity.window.decorView,"Senden")!!.performClick()
            }
            await("History edit did not reuse the already open search") {
                WorkflowService.run?.let { WorkflowAiPolicy.verified(it) && it.steps.last().value == "Silber" } == true
            }
            val node = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
            assertEquals("Silber",node.text.toString())
            val entries = WorkflowResultStore.history(context,app)
            assertEquals(2,entries.size); assertEquals("Nimm Silber statt Gold",entries.last().optString("request"))
            assertEquals(0,WorkflowResultStore.history(context,"org.other.app").size)
        } finally { main { activity.finish() } }
    }
    @Test fun newestOwnerRequestReplacesPendingSequenceAndInvalidatesOldAnswers() {
        main {
            val service = WorkflowService.instance!!
            assertTrue(service.begin(app, listOf(WorkflowStep(WorkflowAction.WAIT, "Never appears"),
                WorkflowStep(WorkflowAction.WRITE, WorkflowSearch.FIELD, "Gold"))))
            val old = WorkflowService.run!!
            val oldEpoch = WorkflowService.epoch
            assertTrue(service.beginAutomatic(app, "Schreibe Silber in das Suchfeld", false))
            assertTrue(old.finished)
            assertTrue(WorkflowService.epoch > oldEpoch)
        }
        context.startActivity(Intent().setClassName(app, app + ".MainActivity").putExtra("mode", "open")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Replacement was not verified") { WorkflowService.run?.let { WorkflowAiPolicy.verified(it) } == true }
        val field = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
        assertEquals("Silber", field.text.toString())
    }
    @Test fun stopAndRejectedReplacementCannotResumePreviousRun() {
        context.startActivity(Intent().setClassName(app, app + ".MainActivity").putExtra("mode", "open")
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
        await("Fixture missing") { automation.rootInActiveWindow?.packageName?.toString() == app }
        main {
            val service = WorkflowService.instance!!
            val steps = listOf(WorkflowStep(WorkflowAction.WRITE, WorkflowSearch.FIELD, "Must not appear"))
            assertTrue(service.begin(app, steps))
            val first = WorkflowService.run!!
            val beforeStop = WorkflowService.epoch
            WorkflowService.stop()
            assertTrue(first.finished); assertNull(WorkflowService.run)
            assertTrue(WorkflowService.epoch > beforeStop)
            assertTrue(service.begin(app, steps))
            val second = WorkflowService.run!!
            assertFalse(service.beginAutomatic(app, "", false))
            assertTrue(second.finished); assertNull(WorkflowService.run)
        }
        SystemClock.sleep(1500) // Let any stale scheduled polls run; none may write.
        val field = automation.rootInActiveWindow.findAccessibilityNodeInfosByViewId(app + ":id/search_src_text").single()
        assertTrue(field.isShowingHintText || field.text.isNullOrBlank())
        assertNull(WorkflowService.run)
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
            val root = automation.rootInActiveWindow
            val visible = root?.findAccessibilityNodeInfosByText("Senden")?.any { it.isVisibleToUser && it.isClickable && it.text?.toString() == "Senden" } == true
            fun scroll(node: android.view.accessibility.AccessibilityNodeInfo): Boolean {
                if (node.isScrollable && node.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)) return true
                for (i in 0 until node.childCount) node.getChild(i)?.let { if (scroll(it)) return true }
                return false
            }
            if (!visible && root != null) scroll(root)
            visible
        }
        val input = automation.rootInActiveWindow.findAccessibilityNodeInfosByText("Auftrag eingeben").single { it.isEditable }
        assertTrue(input.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_SET_TEXT, android.os.Bundle().apply {
            putCharSequence(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,"Gold")
        }))
        val start = automation.rootInActiveWindow.findAccessibilityNodeInfosByText("Senden").single { it.isClickable && it.text?.toString() == "Senden" }
        assertTrue(start.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
        await("DEGIRO reader handoff missing") {
            automation.rootInActiveWindow?.findAccessibilityNodeInfosByText("DEGIRO lesen · Produkt und Morgenliste")?.isNotEmpty() == true
        }
        assertFalse(GoldSearchRun.running) // Fixture device has no enabled product reader.
        assertNull(WorkflowService.run)
        assertTrue(automation.rootInActiveWindow.findAccessibilityNodeInfosByText("Lesedienst zuerst einschalten.").isNotEmpty())
        context.getSharedPreferences("workflow_auto_v1",0).edit().clear().commit()
    }
    @Test fun ownerLoginRequestUsesLocalPinRouteAndShowsMissingReaderInsteadOfAiRejection() {
        context.getSharedPreferences("workflow_auto_v1",0).edit()
            .putString("lastApp",WorkflowAppRoute.DEGIRO).commit()
        val previous = context.getSharedPreferences("product_reader",0).getBoolean("enabled",false)
        context.getSharedPreferences("product_reader",0).edit().putBoolean("enabled",false).commit()
        val monitor = instrumentation.addMonitor(ProductReadActivity::class.java.name,null,false)
        val activity = instrumentation.startActivitySync(Intent(context,WorkflowActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as WorkflowActivity
        try {
            main {
                val input = WorkflowActivity::class.java.getDeclaredField("goal").apply { isAccessible = true }.get(activity) as android.widget.EditText
                input.setText("öffne degiro und gebe selbstständig das Passwort ein zum Öffnen der App")
                WorkflowActivity::class.java.getDeclaredMethod("sendMessage").apply { isAccessible = true }.invoke(activity)
            }
            val reader = instrumentation.waitForMonitorWithTimeout(monitor,5000) as? ProductReadActivity
            assertNotNull("Local PIN reader was not opened",reader)
            await("Missing reader should be explained locally") {
                automation.rootInActiveWindow?.findAccessibilityNodeInfosByText("Lokale DEGIRO-Anmeldung: Lesedienst zuerst einschalten.")?.isNotEmpty() == true
            }
            main {
                assertFalse(reader!!.intent.hasExtra(ProductReadActivity.EXTRA_CAPABILITY))
                val actions = ProductReadActivity::class.java.getDeclaredField("capabilityActions").apply { isAccessible = true }.get(reader) as Map<*,*>
                assertTrue(actions.keys.containsAll(WorkflowAppRoute.capabilities.map { it.title }))
                assertNull(WorkflowService.run)
                assertFalse(PinReadinessProbe.running)
                assertFalse(GoldSearchRun.running)
                assertFalse(LoginToReadHandoff.pending(SystemClock.elapsedRealtime()))
                reader.finish()
            }
        } finally {
            instrumentation.removeMonitor(monitor)
            main { activity.finish() }
            context.getSharedPreferences("product_reader",0).edit().putBoolean("enabled",previous).commit()
            context.getSharedPreferences("workflow_auto_v1",0).edit().clear().commit()
        }
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
