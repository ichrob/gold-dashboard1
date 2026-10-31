package ch.bob.degirocompanion

import android.graphics.Rect
import android.os.Build
import android.os.SystemClock
import android.view.accessibility.AccessibilityNodeInfo
import ch.bob.degirocompanion.PinKeypadExerciseTrace.Reason
import ch.bob.degirocompanion.PinKeypadExerciseTrace.Stage

/** One bounded touch on the validated zero node; deletion remains a direct node action.
 * After dispatch, never reads input text or traverses the tree. */
internal class PinKeypadExercise(private val confirmedEmpty: Boolean,
    private val digitTouch: ((AccessibilityNodeInfo, Rect, Int, (Boolean) -> Unit) -> Boolean)?) {
    private val policy = PinKeypadExercisePolicy()
    val trace = PinKeypadExerciseTrace()
    private var target: AccessibilityNodeInfo? = null
    private var targetBounds = Rect()
    private var targetClass: String? = null
    private var targetViewId: String? = null
    private var window = -1
    private var boundsRecovery: PinBoundsRecovery<Rect>? = null
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
    private fun bounds(node: AccessibilityNodeInfo) = Rect().also { node.getBoundsInScreen(it) }

    fun begin(root: AccessibilityNodeInfo, zero: AccessibilityNodeInfo, delete: AccessibilityNodeInfo) {
        if (armed || done) return
        val id = root.windowId
        val zeroBounds = bounds(zero)
        val deleteBounds = bounds(delete)
        // The caller already checked a complete login scene, unique regular 0..9 grid,
        // direct digit actions and the exact user-confirmed lower-right symbol position.
        val valid = allowed(root, id) && zero.refresh() && delete.refresh() &&
            allowed(zero, id) && allowed(delete, id) && zero.isEnabled && !delete.isEnabled &&
            clickOffered(zero) && clickOffered(delete) && bounds(zero) == zeroBounds &&
            bounds(delete) == deleteBounds &&
            (PinKeypadPolicy.digit(zero.text) ?: PinKeypadPolicy.digit(zero.contentDescription)) == 0
        if (policy.begin(confirmedEmpty, valid) != PinKeypadExercisePolicy.Action.DIGIT) return
        window = id
        target = AccessibilityNodeInfo.obtain(delete)
        targetClass = delete.className?.toString()
        targetViewId = delete.viewIdResourceName
        delete.getBoundsInScreen(targetBounds)
        boundsRecovery = PinBoundsRecovery(Rect(targetBounds), SystemClock.elapsedRealtime() + 12_000)
        code = "KEYPAD_TEST_DIGIT_SENT"
        trace.advance(Stage.DIGIT_REQUESTED)
        val accepted = digitTouch?.invoke(zero, Rect(zeroBounds), window) { completed ->
            policy.digitCompleted(completed)
            if (!completed) abort(reason = Reason.DIGIT_TOUCH_CANCELLED)
        } == true
        if (!accepted) abort("KEYPAD_TEST_DIGIT_REJECTED", Reason.DIGIT_REJECTED)
        else trace.advance(Stage.DIGIT_ACCEPTED)
    }

    fun inspect(root: AccessibilityNodeInfo?) {
        if (!armed || done) return
        val node = target
        val reason = when {
            root == null -> Reason.ROOT_MISSING
            root.packageName?.toString() != ProductScreenEvidence.PACKAGE -> Reason.ROOT_PACKAGE
            root.windowId != window -> Reason.ROOT_WINDOW
            !root.isVisibleToUser -> Reason.ROOT_HIDDEN
            root.isPassword || root.isEditable || (Build.VERSION.SDK_INT >= 34 && root.isAccessibilityDataSensitive) -> Reason.ROOT_PROTECTED
            node == null -> Reason.TARGET_MISSING
            !node.refresh() -> Reason.TARGET_REFRESH_FAILED
            node.packageName?.toString() != ProductScreenEvidence.PACKAGE -> Reason.TARGET_PACKAGE
            node.windowId != window -> Reason.TARGET_WINDOW
            !node.isVisibleToUser -> Reason.TARGET_HIDDEN
            node.isPassword || node.isEditable || (Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive) -> Reason.TARGET_PROTECTED
            !clickOffered(node) -> Reason.TARGET_ACTION_UNAVAILABLE
            node.className?.toString() != targetClass -> Reason.TARGET_CLASS_CHANGED
            node.viewIdResourceName != targetViewId -> Reason.TARGET_ID_CHANGED
            else -> Reason.NONE
        }
        if (reason != Reason.NONE) { abort(reason = reason); return }
        checkNotNull(node)
        val recovery = checkNotNull(boundsRecovery)
        when (recovery.observe(bounds(node), SystemClock.elapsedRealtime())) {
            PinBoundsRecovery.Decision.WAIT -> { policy.pauseObservation(); return }
            PinBoundsRecovery.Decision.EXPIRED -> {
                if (recovery.movementPending) abort(reason = Reason.TARGET_BOUNDS_CHANGED)
                else abort("KEYPAD_TEST_NO_STATE_CHANGE", Reason.STATE_TIMEOUT)
                return
            }
            PinBoundsRecovery.Decision.READY -> Unit
        }
        when (policy.observe(true, node.isEnabled)) {
            PinKeypadExercisePolicy.Action.DELETE -> {
                code = "KEYPAD_TEST_DELETE_SENT"
                trace.advance(Stage.DELETE_REQUESTED)
                if (!node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) abort("KEYPAD_TEST_DELETE_REJECTED", Reason.DELETE_REJECTED)
                else trace.advance(Stage.DELETE_ACCEPTED)
            }
            PinKeypadExercisePolicy.Action.FINISH -> {
                code = "KEYPAD_TEST_STATE_CYCLE_OBSERVED"; trace.end(Reason.STATE_CYCLE); done = true; release()
            }
            else -> Unit
        }
    }
    fun abort(resultCode: String = "KEYPAD_TEST_INTERRUPTED", reason: Reason = Reason.STOPPED) {
        if (!done) { code = resultCode; trace.end(reason); done = true; policy.stop() }
        release()
    }
    private fun release() { target?.recycle(); target = null }
    val message get() = when (code) {
        "KEYPAD_TEST_STATE_CYCLE_OBSERVED" -> "Ein Testzifferndruck und ein Löschdruck wurden angenommen; deaktiviert → aktiv → deaktiviert beobachtet. Bitte selbst prüfen, dass alle fünf Felder leer sind. Kein Nachweis einer Anmeldung oder automatisch erkannten leeren Eingabe."
        "KEYPAD_TEST_WAITING" -> "Bedienungstest wartet auf die eindeutig erkennbare PIN-Tastatur mit deaktivierter Löschtaste."
        else -> "Bedienungstest: $code. Schritt: ${trace.stage}; Grund: ${trace.reason}. Keine Wiederholung. Bitte in DEGIRO prüfen und eine eventuell verbliebene Testziffer selbst löschen."
    }
}

