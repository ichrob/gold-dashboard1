package ch.bob.degirocompanion

import android.graphics.Rect
import android.os.Build
import android.os.SystemClock
import android.view.accessibility.AccessibilityNodeInfo

/** Uses only direct node actions. After the single test digit, never reads text or traverses the tree. */
internal class PinKeypadExercise(private val confirmedEmpty: Boolean) {
    private val policy = PinKeypadExercisePolicy()
    private var target: AccessibilityNodeInfo? = null
    private var targetBounds = Rect()
    private var targetClass: String? = null
    private var targetViewId: String? = null
    private var window = -1
    private var expires = 0L
    var code = "KEYPAD_TEST_WAITING"
        private set
    var done = false
        private set
    val armed get() = policy.issuedDigit

    private fun allowed(node: AccessibilityNodeInfo, expectedWindow: Int): Boolean =
        node.packageName?.toString() == ProductScreenEvidence.PACKAGE && node.windowId == expectedWindow &&
        node.isVisibleToUser && !node.isPassword && !node.isEditable &&
        !(Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive)
    private fun clickOffered(node: AccessibilityNodeInfo) = node.isClickable &&
        node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK }

    fun begin(root: AccessibilityNodeInfo, zero: AccessibilityNodeInfo, delete: AccessibilityNodeInfo) {
        if (armed || done) return
        val id = root.windowId
        // The caller already checked a complete login scene, unique regular 0..9 grid,
        // direct digit actions and the exact user-confirmed lower-right symbol position.
        val valid = allowed(root, id) && zero.refresh() && delete.refresh() &&
            allowed(zero, id) && allowed(delete, id) && zero.isEnabled && !delete.isEnabled &&
            clickOffered(zero) && clickOffered(delete)
        if (policy.begin(confirmedEmpty, valid) != PinKeypadExercisePolicy.Action.DIGIT) return
        window = id
        target = AccessibilityNodeInfo.obtain(delete)
        targetClass = delete.className?.toString()
        targetViewId = delete.viewIdResourceName
        delete.getBoundsInScreen(targetBounds)
        expires = SystemClock.elapsedRealtime() + 12_000
        code = "KEYPAD_TEST_DIGIT_SENT"
        if (!zero.performAction(AccessibilityNodeInfo.ACTION_CLICK)) abort("KEYPAD_TEST_DIGIT_REJECTED")
    }

    fun inspect(root: AccessibilityNodeInfo?) {
        if (!armed || done) return
        val node = target
        if (root == null || node == null || !allowed(root, window) || !node.refresh() ||
            !allowed(node, window) || !clickOffered(node)) {
            abort("KEYPAD_TEST_INTERRUPTED"); return
        }
        val bounds = Rect(); node.getBoundsInScreen(bounds)
        if (bounds != targetBounds || node.className?.toString() != targetClass ||
            node.viewIdResourceName != targetViewId) { abort("KEYPAD_TEST_INTERRUPTED"); return }
        if (SystemClock.elapsedRealtime() >= expires) { abort("KEYPAD_TEST_NO_STATE_CHANGE"); return }
        when (policy.observe(true, node.isEnabled)) {
            PinKeypadExercisePolicy.Action.DELETE -> {
                code = "KEYPAD_TEST_DELETE_SENT"
                if (!node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) abort("KEYPAD_TEST_DELETE_REJECTED")
            }
            PinKeypadExercisePolicy.Action.FINISH -> {
                code = "KEYPAD_TEST_STATE_CYCLE_OBSERVED"; done = true; release()
            }
            else -> Unit
        }
    }
    fun abort(reason: String = "KEYPAD_TEST_INTERRUPTED") {
        if (!done) { code = reason; done = true; policy.stop() }
        release()
    }
    private fun release() { target?.recycle(); target = null }
    val message get() = when (code) {
        "KEYPAD_TEST_STATE_CYCLE_OBSERVED" -> "Ein Testzifferndruck und ein Löschdruck wurden angenommen; deaktiviert → aktiv → deaktiviert beobachtet. Bitte selbst prüfen, dass alle fünf Felder leer sind. Kein Nachweis einer Anmeldung oder automatisch erkannten leeren Eingabe."
        "KEYPAD_TEST_WAITING" -> "Bedienungstest wartet auf die eindeutig erkennbare PIN-Tastatur mit deaktivierter Löschtaste."
        else -> "Bedienungstest: $code. Keine Wiederholung. Bitte in DEGIRO prüfen und eine eventuell verbliebene Testziffer selbst löschen."
    }
}
