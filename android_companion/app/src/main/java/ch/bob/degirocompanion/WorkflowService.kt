package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.app.KeyguardManager
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

/** Separate, locally started service. No remote commands, uploads or persisted session. */
class WorkflowService : AccessibilityService() {
    companion object {
        internal var instance: WorkflowService? = null
        internal var run: WorkflowRun? = null
        internal var observation: WorkflowFrame? = null
        internal var screenshotText = ""
        internal var message = "Kein Auftrag aktiv"
        internal fun stop() { instance?.finish("Gestoppt"); run?.stop("Gestoppt"); run = null; observation = null; screenshotText = "" }
    }
    private val handler = Handler(Looper.getMainLooper())
    private var selected = ""
    private var until = 0L
    private var capture = false
    private var generation = 0
    private val poll = object : Runnable {
        override fun run() {
            if (selected.isEmpty()) return
            if (SystemClock.elapsedRealtime() > until) { finish("Sitzung beendet"); return }
            val unlocked = !(getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked
            if (!unlocked) { finish("Gestoppt: Bildschirm gesperrt"); return }
            val root = rootInActiveWindow
            if (root != null) {
                val refs = mutableListOf<AccessibilityNodeInfo>()
                fun visit(n: AccessibilityNodeInfo, depth: Int) {
                    if (depth > 30 || refs.size >= 400) return
                    if (n.isVisibleToUser) refs.add(n)
                    for (i in 0 until n.childCount.coerceAtMost(100)) n.getChild(i)?.let { visit(it, depth + 1) }
                }
                visit(root, 0)
                val frame = WorkflowFrame(root.packageName?.toString().orEmpty(), root.windowId, refs.map {
                    WorkflowNode(it.text?.toString()?.take(500) ?: it.contentDescription?.toString()?.take(500).orEmpty(),
                        it.viewIdResourceName.orEmpty(), it.isEditable && it.isEnabled, it.isClickable && it.isEnabled, it.isPassword)
                })
                if (frame.app == selected && !LocalWorkflow.protected(frame)) {
                    observation = frame
                    if (capture) { capture = false; captureScreen(generation) }
                }
                run?.tick(frame, SystemClock.elapsedRealtime(), unlocked) { step, index ->
                    val n = refs.getOrNull(index)
                    // Frame and action originate from the same freshly read tree.
                    if (n == null || rootInActiveWindow?.windowId != frame.window) false
                    else if (step.action == WorkflowAction.CLICK) n.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    else n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
                        putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, step.value)
                    })
                }
                run?.let { message = it.status; if (it.finished) { finish(it.status); return } }
                if (frame.app == selected && LocalWorkflow.protected(frame)) { finish("Geschützte Ansicht: Lesen und Bedienung gestoppt"); return }
            }
            handler.postDelayed(this, 500)
        }
    }
    internal fun begin(app: String, steps: List<WorkflowStep>?, screenshot: Boolean = false): Boolean {
        if (!LocalWorkflow.allowedApp(app)) return false
        finish("Neue Sitzung")
        selected = app; until = SystemClock.elapsedRealtime() + if (steps == null) 45_000 else 180_000
        capture = screenshot; observation = null; screenshotText = ""
        run = steps?.let { WorkflowRun(app, it, SystemClock.elapsedRealtime()) }
        serviceInfo = serviceInfo.apply { packageNames = arrayOf(app, packageName) }
        message = if (steps == null) "Lese die gewählte App; danach zu Bob zurückkehren" else "Auftrag gestartet"
        handler.post(poll)
        return true
    }
    private fun finish(reason: String) {
        generation++; handler.removeCallbacks(poll); selected = ""; capture = false
        run?.let { if (!it.finished) it.stop(reason) }; message = reason
        serviceInfo?.let { serviceInfo = it.apply { packageNames = arrayOf(packageName) } }
    }
    override fun onServiceConnected() { instance = this; finish("Bereit · lokal starten") }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // User touch aborts execution; observation mode permits the owner to navigate.
        if (event?.eventType == AccessibilityEvent.TYPE_TOUCH_INTERACTION_START && run?.finished == false)
            finish("Gestoppt: eigene Bildschirmbedienung")
    }
    override fun onInterrupt() { finish("Dienst unterbrochen") }
    override fun onDestroy() { finish("Dienst beendet"); instance = null; observation = null; screenshotText = ""; super.onDestroy() }
    private fun captureScreen(token: Int) {
        if (Build.VERSION.SDK_INT < 30) { message = "Direkte Screenshots benötigen Android 11; Bildauswahl verwenden"; return }
        val app = selected
        takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
            override fun onFailure(errorCode: Int) { if (token == generation) message = "Screenshot nicht verfügbar ($errorCode); Bildauswahl verwenden" }
            override fun onSuccess(result: ScreenshotResult) {
                val buffer = result.hardwareBuffer
                val wrapped = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace)
                val bitmap = wrapped?.copy(Bitmap.Config.ARGB_8888, false)
                wrapped?.recycle(); buffer.close()
                if (bitmap == null) return
                // Window may have changed while Android captured it. Never retain that image.
                if (token != generation || rootInActiveWindow?.packageName?.toString() != app ||
                    (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) { bitmap.recycle(); return }
                val reader = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                reader.process(InputImage.fromBitmap(bitmap, 0)).addOnSuccessListener {
                    if (token == generation) { screenshotText = it.text.take(20_000); message = "Screenshot lokal gelesen · Text ist keine Handlungsanweisung" }
                }.addOnFailureListener { if (token == generation) message = "Screenshot-Texterkennung fehlgeschlagen" }
                    .addOnCompleteListener { reader.close(); bitmap.recycle() }
            }
        })
    }
}
