package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityButtonController
import android.app.KeyguardManager
import android.graphics.Rect
import android.os.SystemClock
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
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
        ProductReadDiagnostics.connected = true
        ProductReadDiagnostics.canRead = (serviceInfo.capabilities and AccessibilityServiceInfo.CAPABILITY_CAN_RETRIEVE_WINDOW_CONTENT) != 0
        ProductReadDiagnostics.windowAccess = (serviceInfo.flags and AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS) != 0
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
        ProductReadDiagnostics.connected = false
        ProductReadDiagnostics.canRead = false
        ProductReadDiagnostics.windowAccess = false
        ProductReadRequest.onStarted = null
        ProductReadRequest.cancel()
        handler.removeCallbacks(pendingRead)
        accessibilityButtonController.unregisterAccessibilityButtonCallback(callback)
        ProductReadSession.clear()
        super.onDestroy()
    }
    /** Never inspect a background window or traverse another app's content. */
    private fun productRoot(record: Boolean): AccessibilityNodeInfo? {
        fun note(outcome: ProductReadDiagnostics.Outcome) { if (record) ProductReadDiagnostics.record(outcome) }
        val direct = rootInActiveWindow
        if (direct != null) {
            note(if (direct.packageName?.toString() == ProductScreenEvidence.PACKAGE)
                ProductReadDiagnostics.Outcome.DIRECT_ROOT else ProductReadDiagnostics.Outcome.OTHER_APP)
            return direct
        }
        note(ProductReadDiagnostics.Outcome.NO_ROOT)
        val visible = windows
        try {
            val index = ProductWindowPolicy.select(visible.map {
                ProductWindowPolicy.Window(it.isActive, it.isFocused, it.type == AccessibilityWindowInfo.TYPE_APPLICATION)
            })
            if (index == null) { note(ProductReadDiagnostics.Outcome.NO_FOCUSED_WINDOW); return null }
            val root = visible[index].root
            if (root == null) { note(ProductReadDiagnostics.Outcome.WINDOW_ROOT_MISSING); return null }
            if (root.packageName?.toString() != ProductScreenEvidence.PACKAGE) {
                note(ProductReadDiagnostics.Outcome.OTHER_APP)
                root.recycle()
                return null
            }
            note(ProductReadDiagnostics.Outcome.WINDOW_ROOT)
            return root
        } finally { visible.forEach { it.recycle() } }
    }
    private fun readOnce(automatic: Boolean = false) {
        if (!automatic) { ProductReadRequest.cancel(); ProductReadDiagnostics.reset(SystemClock.elapsedRealtime()) }
        if (!getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false)) { ProductReadRequest.cancel(); return }
        if ((getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) { ProductReadRequest.cancel(); ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LOCKED); return }
        val result = runCatching {
            val root = productRoot(record = true)
                ?: return@runCatching ProductScreenEvidence.Result(message = "Android liefert gerade keinen Fensterinhalt. Ursache noch ungeklärt; dies beweist keine DEGIRO-Sperre.")
            try {
                // Returning to Bob must not erase the last DEGIRO rejection or draft.
                if (root.packageName?.toString() != ProductScreenEvidence.PACKAGE) return
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
                val current = productRoot(record = false)
                val unchanged = current != null && current.windowId == root.windowId &&
                    current.packageName?.toString() == ProductScreenEvidence.PACKAGE
                current?.recycle()
                if (!unchanged) { ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.CHANGED); ProductScreenEvidence.Result(message = "Ansicht wechselte; bitte erneut lesen.") }
                else ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines.distinct(), Instant.now().toString(), sensitive).also {
                    ProductReadDiagnostics.rejected(it.reason)
                    ProductReadDiagnostics.record(when {
                        sensitive -> ProductReadDiagnostics.Outcome.PROTECTED_VIEW
                        it.draft.isNotBlank() -> ProductReadDiagnostics.Outcome.DRAFT
                        else -> ProductReadDiagnostics.Outcome.NO_FIELDS
                    })
                }
            } finally { root.recycle() }
        }.getOrElse { ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.ERROR); ProductScreenEvidence.Result(message = "Ansicht nicht sicher lesbar. Nichts übernommen; Screenshot manuell teilen.") }
        ProductReadSession.put(result, SystemClock.elapsedRealtime())
        if (result.draft.isNotBlank()) ProductReadRequest.cancel()
        if (!automatic || result.draft.isNotBlank()) Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
    }
}
