package ch.bob.degirocompanion

import android.graphics.Rect
import android.os.Build
import android.os.SystemClock
import android.view.accessibility.AccessibilityNodeInfo

/** A locally confirmed single sequence. No input reads after the first dispatch, no retry, no orders. */
internal class LocalPinLogin(pin: ByteArray,
    private val touch: ((AccessibilityNodeInfo, Rect, Int, (Boolean) -> Unit) -> Boolean)?) {
    private val sequence = LocalPinSequence(pin)
    private data class Target(val node: AccessibilityNodeInfo, val bounds: Rect, val type: String?, val id: String?)
    private val targets = mutableListOf<Target>()
    private var window = -1
    private var expires = 0L
    var afterEntry = false
        private set
    var armed = false
        private set
    var done = false
        private set
    var code = "LOCAL_PIN_WAITING"
        private set
    val touchExpected get() = armed && !done && sequence.pending
    private fun bounds(n: AccessibilityNodeInfo) = Rect().also { n.getBoundsInScreen(it) }
    private fun allowed(n: AccessibilityNodeInfo) = n.packageName?.toString() == ProductScreenEvidence.PACKAGE &&
        n.windowId == window && n.isVisibleToUser && !n.isPassword && !n.isEditable &&
        !(Build.VERSION.SDK_INT >= 34 && n.isAccessibilityDataSensitive)
    fun begin(root: AccessibilityNodeInfo, digits: List<AccessibilityNodeInfo>) {
        if (armed || done) return
        window = root.windowId
        if (!allowed(root) || digits.size != 10 || digits.withIndex().any { (i,n) ->
                !n.refresh() || !allowed(n) || !n.isEnabled || !n.isClickable ||
                    (PinKeypadPolicy.digit(n.text) ?: PinKeypadPolicy.digit(n.contentDescription)) != i }) {
            abort("LOCAL_PIN_LAYOUT_CHANGED"); return
        }
        digits.forEach { targets += Target(AccessibilityNodeInfo.obtain(it), bounds(it), it.className?.toString(), it.viewIdResourceName) }
        expires = SystemClock.elapsedRealtime() + 20_000
        armed = true
        inspect(root)
    }
    fun inspect(root: AccessibilityNodeInfo?) {
        if (!armed || done || afterEntry) return
        if (SystemClock.elapsedRealtime() >= expires) { abort("LOCAL_PIN_TIMEOUT"); return }
        if (root == null || !allowed(root) || targets.any { t ->
                !t.node.refresh() || !allowed(t.node) || !t.node.isEnabled || !t.node.isClickable ||
                    t.node.actionList.none { it.id == AccessibilityNodeInfo.ACTION_CLICK } ||
                    bounds(t.node) != t.bounds || t.node.className?.toString() != t.type || t.node.viewIdResourceName != t.id }) {
            abort("LOCAL_PIN_LAYOUT_CHANGED"); return
        }
        val digit = sequence.reserve(true) ?: return
        val ticket = sequence.ticket
        val target = targets[digit]
        code = "LOCAL_PIN_ENTERING"
        val accepted = touch?.invoke(target.node, Rect(target.bounds), window) { completed ->
            if (!done) {
                sequence.completed(ticket, completed)
                if (!completed) abort("LOCAL_PIN_TOUCH_CANCELLED")
                else if (sequence.complete) finishEntry("LOCAL_PIN_ENTRY_SENT")
            }
        } == true
        if (!accepted) abort("LOCAL_PIN_TOUCH_REJECTED")
    }
    private fun finishEntry(result: String) {
        if (done || afterEntry) return
        afterEntry = true; code = result; sequence.cancel()
        targets.forEach { it.node.recycle() }; targets.clear()
    }
    fun windowChanged() {
        if (afterEntry || done) return
        if (sequence.lastReserved) finishEntry("LOCAL_PIN_RESULT_UNVERIFIED") else abort("LOCAL_PIN_INTERRUPTED")
    }
    fun abort(result: String = "LOCAL_PIN_INTERRUPTED") {
        if (done) return
        done = true; code = result; sequence.cancel()
        targets.forEach { it.node.recycle() }; targets.clear()
    }
    val message get() = when (code) {
        "LOCAL_PIN_WAITING" -> "Warte auf die eindeutige PIN-Tastatur. Bekannte Biometrie-Dialoge werden einmal geschlossen. Handy nicht bedienen."
        "LOCAL_PIN_HOME_VISIBLE" -> "DEGIRO-Marktseite bestätigt. Ein ausdrücklich gestarteter Gesamttest darf jetzt die Goldproduktsuche beginnen; keine Orders."
        "LOCAL_PIN_ENTERING" -> "Einmalige lokale PIN-Eingabe läuft. Handy nicht bedienen."
        "LOCAL_PIN_ENTRY_SENT", "LOCAL_PIN_RESULT_UNVERIFIED" -> "Einmalige Eingabe beendet. Bitte in DEGIRO prüfen, ob die Anmeldung gelang. Keine automatische Wiederholung und noch kein bestätigter Login."
        else -> "Lokale PIN-Eingabe gestoppt: $code. Bitte DEGIRO selbst prüfen und verbliebene Eingaben löschen. Kein erneuter Versuch durch Bob."
    }
}
