package ch.bob.degirocompanion

import android.os.SystemClock
import android.text.InputType
import android.view.accessibility.AccessibilityNodeInfo

/** Explicit local 30-second inspection. Never performs an action or reads node text. */
internal object PinReadinessProbe {
    private var deadline = 0L
    private val history = PinProbeHistory()
    var message = "Noch kein PIN-Erkennungstest."
        private set
    var onStart: (() -> Unit)? = null
    var onStop: (() -> Unit)? = null
    val running get() = deadline != 0L
    fun start() {
        check(onStart != null) { "Lesedienst zuerst verbinden." }
        history.clear()
        deadline = SystemClock.elapsedRealtime() + 30_000
        message = "Prüfung läuft (30 Sekunden). In DEGIRO die PIN-Anmeldung anzeigen, aber keine PIN eingeben. Danach zu Bob zurückkehren."
        onStart?.invoke()
    }
    fun active(): Boolean {
        if (running && SystemClock.elapsedRealtime() >= deadline) stop("Zeit beendet. " + message)
        return running
    }
    fun stop(reason: String) {
        deadline = 0L
        message = reason
        onStop?.invoke()
    }
    fun inspect(root: AccessibilityNodeInfo?) {
        if (!active()) return
        if (root == null || root.packageName?.toString() != ProductScreenEvidence.PACKAGE) {
            history.observe(null)
            message = history.last?.let { "Letzte DEGIRO-Beobachtung (Fenster jetzt nicht zugänglich): " + describe(it) }
                ?: "Während dieses Tests noch kein zugängliches DEGIRO-Fenster. PIN-Bedienbarkeit ungeklärt."
            return
        }
        val fields = mutableListOf<PinProbePolicy.Field>()
        var count = 0
        var complete = true
        fun visit(node: AccessibilityNodeInfo, depth: Int) {
            if (++count > 300 || depth > 25) { complete = false; return }
            if (!node.isVisibleToUser) return
            if (node.packageName?.toString() != ProductScreenEvidence.PACKAGE) { complete = false; return }
            val sensitive = android.os.Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive
            fields += PinProbePolicy.Field(node.isPassword,
                node.inputType and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_NUMBER,
                node.isEditable, node.isEnabled,
                node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_SET_TEXT }, sensitive)
            // No inspection of protected descendants, labels, IDs, descriptions or values.
            if (sensitive) return
            for (i in 0 until node.childCount) {
                if (count >= 300) { complete = false; break }
                val child = node.getChild(i) ?: continue
                try { visit(child, depth + 1) } finally { child.recycle() }
            }
        }
        val outcome = runCatching { visit(root, 0); PinProbePolicy.classify(fields, complete) }
            .getOrDefault(PinProbePolicy.Result.INCOMPLETE)
        history.observe(outcome)
        message = describe(outcome)
    }
    private fun describe(outcome: PinProbePolicy.Result): String = when (outcome) {
            PinProbePolicy.Result.SET_TEXT_OFFERED -> "Numerisches Passwortfeld bietet Texteingabe an. PIN-Seite und tatsächliche Eingabefunktion sind damit noch nicht bestätigt."
            PinProbePolicy.Result.NUMERIC_PASSWORD_INPUT -> "Numerisches Passwortfeld sichtbar; automatische Eingabe nicht nachgewiesen."
            PinProbePolicy.Result.SENSITIVE_INPUT -> "Android markiert Eingabeelemente als geschützt. Bedienbarkeit ungeklärt."
            PinProbePolicy.Result.INPUT_PRESENT -> "Eingabeelement vorhanden; keine eindeutige numerische PIN-Eingabe erkannt."
            PinProbePolicy.Result.NO_INPUT -> "Kein PIN-Eingabefeld erkannt. Eine eigene Bildschirmtastatur oder verdeckte Ansicht bleibt möglich."
            PinProbePolicy.Result.INCOMPLETE -> "Ansicht nicht vollständig prüfbar. Keine Aussage zur PIN-Eingabe."
        }
}
