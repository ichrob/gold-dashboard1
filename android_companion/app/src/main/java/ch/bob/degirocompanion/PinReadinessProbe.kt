package ch.bob.degirocompanion

import android.os.SystemClock
import android.text.InputType
import android.view.accessibility.AccessibilityNodeInfo

/** Explicit local 30-second inspection. Never performs actions. Only fixed non-input UI markers are matched locally. */
internal object PinReadinessProbe {
    private var deadline = 0L
    var reportId = ""
        private set
    var finished = false
        private set
    val resultCode get() = history.last?.name ?: "NO_WINDOW"
    var onTimeout: (() -> Unit)? = null
    private val history = PinProbeHistory()
    var message = "Noch kein PIN-Erkennungstest."
        private set
    var onStart: (() -> Unit)? = null
    var onStop: (() -> Unit)? = null
    val running get() = deadline != 0L
    fun start() {
        check(onStart != null) { "Lesedienst zuerst verbinden." }
        history.clear()
        reportId = java.util.UUID.randomUUID().toString().replace("-", "")
        finished = false
        deadline = SystemClock.elapsedRealtime() + 30_000
        message = "Prüfung läuft (30 Sekunden). In DEGIRO die PIN-Anmeldung anzeigen, aber keine PIN eingeben. Bob versucht danach automatisch zur Ergebnisanzeige zurückzukehren."
        onStart?.invoke()
    }
    fun active(): Boolean {
        if (running && SystemClock.elapsedRealtime() >= deadline) {
            finished = true
            stop("Zeit beendet. " + message)
            onTimeout?.invoke()
        }
        return running
    }
    fun stop(reason: String) {
        val wasRunning = running
        deadline = 0L
        message = reason
        if (wasRunning) onStop?.invoke()
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
        val keys = mutableListOf<PinKeypadPolicy.Key>()
        var loginHelp = false
        var setup = false
        val resetEvidence = PinResetEvidence()
        var count = 0
        var complete = true
        fun visit(node: AccessibilityNodeInfo, depth: Int, parentOwner: Int? = null, ownerDepth: Int = 0) {
            if (++count > 300 || depth > 25) { complete = false; return }
            if (!node.isVisibleToUser) return
            if (node.packageName?.toString() != ProductScreenEvidence.PACKAGE) { complete = false; return }
            val sensitive = android.os.Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive
            fields += PinProbePolicy.Field(node.isPassword,
                node.inputType and InputType.TYPE_MASK_CLASS == InputType.TYPE_CLASS_NUMBER,
                node.isEditable, node.isEnabled,
                node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_SET_TEXT }, sensitive)
            // Never read input values or protected descendants. No labels leave this method.
            if (sensitive || node.isPassword || node.isEditable) {
                resetEvidence.block(parentOwner)
                return
            }
            val clickable = node.isEnabled && node.isClickable &&
                node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK }
            // A container with a separate clickable descendant cannot own that descendant's label.
            if (clickable) resetEvidence.block(parentOwner)
            val owner = if (clickable) count else parentOwner
            val actionDepth = if (clickable) depth else ownerDepth
            if (!node.isEnabled) resetEvidence.block(owner)
            run {
                val labels = listOf(node.text, node.contentDescription)
                val markers = labels.map { PinLoginEvidence.marker(it) }
                loginHelp = loginHelp || PinLoginEvidence.Marker.LOGIN_HELP in markers
                setup = setup || PinLoginEvidence.Marker.BIOMETRIC_SETUP in markers
                val unrelated = labels.indices.any { i ->
                    !labels[i].isNullOrBlank() && markers[i] != PinLoginEvidence.Marker.DELETE_KEY
                }
                resetEvidence.observe(owner, depth - actionDepth,
                    PinLoginEvidence.Marker.DELETE_KEY in markers, unrelated, node.isEnabled)
            }
            if (node.childCount == 0 && node.isEnabled) {
                val digit = PinKeypadPolicy.digit(node.text) ?: PinKeypadPolicy.digit(node.contentDescription)
                if (digit != null) keys += PinKeypadPolicy.Key(digit,
                    node.isClickable && node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK })
            }
            for (i in 0 until node.childCount) {
                if (count >= 300) { complete = false; break }
                val child = node.getChild(i) ?: continue
                try { visit(child, depth + 1, owner, actionDepth) } finally { child.recycle() }
            }
        }
        val outcome = runCatching { visit(root, 0)
            val structural = PinProbePolicy.classify(fields, complete)
            if (structural == PinProbePolicy.Result.NO_INPUT)
                PinLoginEvidence.classify(PinKeypadPolicy.classify(keys) ?: structural,
                    loginHelp, setup, resetEvidence.count()).let {
                    if (it == PinProbePolicy.Result.LOGIN_RESET_UNCONFIRMED) resetEvidence.diagnosis() else it
                } else structural }
            .getOrDefault(PinProbePolicy.Result.INCOMPLETE)
        history.observe(outcome)
        message = describe(outcome)
    }
    private fun describe(outcome: PinProbePolicy.Result): String = when (outcome) {
            PinProbePolicy.Result.LOGIN_DELETE_LABEL_UNRECOGNIZED -> "Keine bekannte Löschtasten-Beschriftung zugänglich. Die Taste kann unbeschriftet, anders beschriftet oder nicht zugänglich sein."
            PinProbePolicy.Result.LOGIN_DELETE_DISABLED -> "Löschtasten-Beschriftung erkannt, aber Element deaktiviert. Das beweist allein keine leere PIN-Eingabe."
            PinProbePolicy.Result.LOGIN_DELETE_NO_ACTION -> "Löschtasten-Beschriftung erkannt; keine zugehörige Klickaktion innerhalb der geprüften zwei Ebenen."
            PinProbePolicy.Result.LOGIN_DELETE_SHARED_TARGET -> "Löschtasten-Beschriftung erkannt; Klickziel wegen weiterer Inhalte oder Unterelemente nicht eindeutig zuordenbar."
            PinProbePolicy.Result.LOGIN_DELETE_AMBIGUOUS -> "Mehrere unterschiedliche Löschtasten-Klickziele erkannt. Keine Taste gedrückt."
            PinProbePolicy.Result.LOGIN_SETUP_VISIBLE -> "Biometrie-Einrichtungshinweis noch sichtbar. Keine Anmeldeeingabe freigegeben."
            PinProbePolicy.Result.LOGIN_DELETE_OFFERED -> "Anmeldehinweis, zehn Zifferntasten und eine Löschtaste mit Klickaktion erkannt. Löschen und Anmeldung noch nicht ausgeführt oder bestätigt."
            PinProbePolicy.Result.LOGIN_RESET_UNCONFIRMED -> "Anmeldehinweis und zehn Zifferntasten erkannt; keine eindeutige bedienbare Löschtaste. Leere PIN-Eingabe nicht bestätigt."
            PinProbePolicy.Result.KEYPAD_CLICK_OFFERED -> "Alle zehn Zifferntasten bieten eine Klickaktion an. Keine Taste gedrückt; PIN-Anmeldung noch nicht nachgewiesen."
            PinProbePolicy.Result.KEYPAD_VISIBLE -> "Alle zehn Zifferntasten erkannt; nicht alle bieten direkt eine Klickaktion an. Keine Taste gedrückt."
            PinProbePolicy.Result.KEYPAD_AMBIGUOUS -> "Zifferntasten mehrfach vorhanden; keine eindeutige Zuordnung. Keine Taste gedrückt."
            PinProbePolicy.Result.SET_TEXT_OFFERED -> "Numerisches Passwortfeld bietet Texteingabe an. PIN-Seite und tatsächliche Eingabefunktion sind damit noch nicht bestätigt."
            PinProbePolicy.Result.NUMERIC_PASSWORD_INPUT -> "Numerisches Passwortfeld sichtbar; automatische Eingabe nicht nachgewiesen."
            PinProbePolicy.Result.SENSITIVE_INPUT -> "Android markiert Eingabeelemente als geschützt. Bedienbarkeit ungeklärt."
            PinProbePolicy.Result.INPUT_PRESENT -> "Eingabeelement vorhanden; keine eindeutige numerische PIN-Eingabe erkannt."
            PinProbePolicy.Result.NO_INPUT -> "Kein PIN-Eingabefeld erkannt. Eine eigene Bildschirmtastatur oder verdeckte Ansicht bleibt möglich."
            PinProbePolicy.Result.INCOMPLETE -> "Ansicht nicht vollständig prüfbar. Keine Aussage zur PIN-Eingabe."
        }
}
