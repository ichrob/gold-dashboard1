package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityButtonController
import android.app.KeyguardManager
import android.graphics.Rect
import android.os.SystemClock
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Toast
import java.time.Instant

/** Explicit one-minute reading request or accessibility button; no UI actions. */
class ProductReadService : AccessibilityService() {
    private val handler = Handler(Looper.getMainLooper())
    private var readQueued = false
    private val pendingRead = object : Runnable {
        override fun run() {
            readQueued = false
            if (ProductReadRequest.attempt(SystemClock.elapsedRealtime())) readOnce(automatic = true)
            if (ProductReadRequest.active(SystemClock.elapsedRealtime())) queueRead(2000)
        }
    }
    private fun queueRead(delay: Long) {
        if (!readQueued && ProductReadRequest.active(SystemClock.elapsedRealtime())) {
            readQueued = true
            handler.postDelayed(pendingRead, delay)
        }
    }
    private val callback = object : AccessibilityButtonController.AccessibilityButtonCallback() {
        override fun onClicked(controller: AccessibilityButtonController) { readOnce() }
    }
    override fun onServiceConnected() {
        accessibilityButtonController.registerAccessibilityButtonCallback(callback)
        ProductReadRequest.onStarted = {
            handler.removeCallbacks(pendingRead)
            readQueued = false
            queueRead(600)
        }
        queueRead(600)
    }
    // Only package/type metadata is used. Never read or retain event text.
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!ProductReadRequest.active(SystemClock.elapsedRealtime())) return
        if (event?.packageName?.toString() != ProductScreenEvidence.PACKAGE) return
        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
            event.eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return
        queueRead(400)
    }
    override fun onInterrupt() { ProductReadRequest.cancel(); handler.removeCallbacks(pendingRead); readQueued = false; ProductReadSession.clear() }
    override fun onDestroy() {
        ProductReadRequest.onStarted = null
        ProductReadRequest.cancel()
        handler.removeCallbacks(pendingRead)
        accessibilityButtonController.unregisterAccessibilityButtonCallback(callback)
        ProductReadSession.clear()
        super.onDestroy()
    }
    private fun readOnce(automatic: Boolean = false) {
        if (!automatic) ProductReadRequest.cancel()
        ProductReadSession.clear()
        if (!getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false)) { ProductReadRequest.cancel(); return }
        if ((getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) { ProductReadRequest.cancel(); return }
        val result = runCatching {
            val root = rootInActiveWindow
                ?: return@runCatching ProductScreenEvidence.Result(message = "Android liefert gerade keinen Fensterinhalt. Ursache noch ungeklärt; dies beweist keine DEGIRO-Sperre.")
            try {
                if (root.packageName?.toString() != ProductScreenEvidence.PACKAGE)
                    return@runCatching ProductScreenEvidence.Result(message = "Bitte zuerst die DEGIRO-Produktseite öffnen.")
                val lines = mutableListOf<QuoteLayout.Line>()
                var sensitive = false
                var count = 0
                fun collect(node: AccessibilityNodeInfo, depth: Int) {
                    check(++count <= 1000 && depth <= 40) { "View too large" }
                    if (!node.isVisibleToUser) return
                    if (node.packageName?.toString() != ProductScreenEvidence.PACKAGE) return
                    if (node.isPassword || node.isEditable) { sensitive = true; return }
                    if (android.os.Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive) { sensitive = true; return }
                    val bounds = Rect(); node.getBoundsInScreen(bounds)
                    val value = (node.text ?: node.contentDescription)?.toString()?.trim()
                    if (!value.isNullOrEmpty() && !bounds.isEmpty) {
                        check(value.length <= 2000)
                        lines += QuoteLayout.Line(value, bounds.left, bounds.top, bounds.right, bounds.bottom)
                    }
                    for (i in 0 until node.childCount) {
                        val child = node.getChild(i) ?: continue
                        try { collect(child, depth + 1) } finally { child.recycle() }
                    }
                }
                collect(root, 0)
                // Reject navigation during traversal; never combine two screens.
                val current = rootInActiveWindow
                val unchanged = current != null && current.windowId == root.windowId &&
                    current.packageName?.toString() == ProductScreenEvidence.PACKAGE
                current?.recycle()
                if (!unchanged) ProductScreenEvidence.Result(message = "Ansicht wechselte; bitte erneut lesen.")
                else ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines.distinct(), Instant.now().toString(), sensitive)
            } finally { root.recycle() }
        }.getOrElse { ProductScreenEvidence.Result(message = "Ansicht nicht sicher lesbar. Nichts übernommen; Screenshot manuell teilen.") }
        ProductReadSession.put(result, SystemClock.elapsedRealtime())
        if (result.draft.isNotBlank()) ProductReadRequest.cancel()
        if (!automatic || result.draft.isNotBlank()) Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
    }
}
