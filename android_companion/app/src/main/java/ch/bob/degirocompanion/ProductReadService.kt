package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityButtonController
import android.app.KeyguardManager
import android.graphics.Rect
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Toast
import java.time.Instant

/** Reads only on the Android accessibility button. No gestures or node actions. */
class ProductReadService : AccessibilityService() {
    private val callback = object : AccessibilityButtonController.AccessibilityButtonCallback() {
        override fun onClicked(controller: AccessibilityButtonController) { readOnce() }
    }
    override fun onServiceConnected() {
        accessibilityButtonController.registerAccessibilityButtonCallback(callback)
    }
    // Event text is deliberately never read, including login events.
    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() { ProductReadSession.clear() }
    override fun onDestroy() {
        accessibilityButtonController.unregisterAccessibilityButtonCallback(callback)
        ProductReadSession.clear()
        super.onDestroy()
    }
    private fun readOnce() {
        ProductReadSession.clear()
        if (!getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false)) return
        if ((getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) return
        val result = runCatching {
            val root = rootInActiveWindow
                ?: return@runCatching ProductScreenEvidence.Result(message = "DEGIRO gibt keinen lesbaren Fensterinhalt frei. Screenshot manuell teilen.")
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
        Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
    }
}
