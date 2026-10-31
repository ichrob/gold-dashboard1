package ch.bob.degirocompanion

import android.os.SystemClock
import android.graphics.Rect
import android.text.InputType
import android.view.accessibility.AccessibilityNodeInfo

/** Default: read-only 30-second inspection. Separate explicit exercise: one test digit and one delete at most. */
internal object PinReadinessProbe {
    private var deadline = 0L
    var reportId = ""
        private set
    var finished = false
        private set
    private var exercise: PinKeypadExercise? = null
    private var login: LocalPinLogin? = null
    private var loginDialogs: LocalLoginDialogs? = null
    val localLoginActive get() = running && login != null
    val loginDialogsAllowed get() = localLoginActive && login?.done == false && (!loginArmed || login?.afterEntry == true)
    fun inspectLoginDialogs(service: android.accessibilityservice.AccessibilityService): Boolean =
        loginDialogsAllowed && loginDialogs?.inspect(service, login?.afterEntry == true) == true
    fun finishLogin(code: String) {
        if (!localLoginActive) return
        login?.abort(code); finished = true; stop(login?.message.orEmpty())
    }
    val loginArmed get() = login?.armed == true
    val loginTouchExpected get() = login?.touchExpected == true
    private val exerciseLayout = PinStableObservation<Pair<Int, List<PinSymbolProbe.Node>>>()
    val exerciseArmed get() = exercise?.armed == true
    val exerciseTrace get() = exercise?.trace
    val resultCode get() = login?.code ?: exercise?.code ?: history.last?.name ?: "NO_WINDOW"
    val symbolFlags get() = if (exercise == null && login == null) history.symbolFlags else null
    var onTimeout: (() -> Unit)? = null
    private val history = PinProbeHistory()
    var message = "Noch kein PIN-Erkennungstest."
        private set
    var onStart: (() -> Unit)? = null
    var onDigitTouch: ((AccessibilityNodeInfo, Rect, Int, (Boolean) -> Unit) -> Boolean)? = null
    var onDeleteTouch: ((AccessibilityNodeInfo, Rect, Int, (Boolean) -> Unit) -> Boolean)? = null
    var onLoginTouch: ((AccessibilityNodeInfo, Rect, Int, (Boolean) -> Unit) -> Boolean)? = null
    var onStop: (() -> Unit)? = null
    val running get() = deadline != 0L
    fun start(confirmedEmptyExercise: Boolean = false) = startInternal(confirmedEmptyExercise, null)
    fun startLocalLogin(pin: ByteArray) = startInternal(false, pin)
    private fun startInternal(confirmedEmptyExercise: Boolean, pin: ByteArray?) {
        check(!running) { "PIN-Test läuft bereits." }
        check(onStart != null && (pin == null || onLoginTouch != null)) { "Lesedienst zuerst verbinden." }
        login?.abort()
        login = if (pin != null) LocalPinLogin(pin, onLoginTouch) else null
        loginDialogs = if (pin != null) LocalLoginDialogs() else null
        exercise?.abort()
        exercise = if (confirmedEmptyExercise) PinKeypadExercise(true, onDigitTouch, onDeleteTouch) else null
        check(onStart != null) { "Lesedienst zuerst verbinden." }
        history.clear()
        exerciseLayout.clear()
        reportId = java.util.UUID.randomUUID().toString().replace("-", "")
        finished = false
        deadline = SystemClock.elapsedRealtime() + if (confirmedEmptyExercise || pin != null) 60_000 else 30_000
        message = "Prüfung läuft (30 Sekunden). In DEGIRO die PIN-Anmeldung anzeigen, aber keine PIN eingeben. Bob versucht danach automatisch zur Ergebnisanzeige zurückzukehren."
        if (exercise != null) message = "Bedienungstest: nur eine Testziffer und ein Löschversuch, keine Anmeldung. Nach dem Schließen der Dialoge nicht weiter bedienen. Maximal 60 Sekunden."
        if (login != null) message = login!!.message
        onStart?.invoke()
    }
    fun active(): Boolean {
        if (running && SystemClock.elapsedRealtime() >= deadline) {
            login?.abort("LOCAL_PIN_TIMEOUT")
            exercise?.abort("KEYPAD_TEST_TIMEOUT", PinKeypadExerciseTrace.Reason.TIMEOUT)
            finished = true
            stop("Zeit beendet. " + (login?.message ?: exercise?.message ?: message))
            if (login == null) onTimeout?.invoke()
        }
        return running
    }
    fun stop(reason: String, exerciseReason: PinKeypadExerciseTrace.Reason = PinKeypadExerciseTrace.Reason.STOPPED) {
        val wasRunning = running
        login?.abort()
        exercise?.abort(reason = exerciseReason)
        deadline = 0L
        exerciseLayout.clear()
        message = reason
        if (wasRunning) onStop?.invoke()
    }
    fun loginWindowChanged() {
        login?.windowChanged()
        if (login?.done == true) { finished = true; stop(login?.message ?: "Lokale Anmeldung beendet.") }
    }
    fun inspect(root: AccessibilityNodeInfo?) {
        if (!active()) return
        if (loginArmed) {
            login?.inspect(root)
            message = login?.message.orEmpty()
            if (login?.done == true) { finished = true; stop(message) }
            return
        }
        if (exerciseArmed) {
            // After input, only cached control metadata is inspected. No labels or input tree traversal.
            exercise?.inspect(root)
            message = exercise?.message.orEmpty()
            if (exercise?.done == true) {
                finished = true
                stop(message)
                onTimeout?.invoke()
            }
            return
        }
        if (root == null || root.packageName?.toString() != ProductScreenEvidence.PACKAGE) {
            exerciseLayout.clear()
            history.observe(null)
            message = history.last?.let { "Letzte DEGIRO-Beobachtung (Fenster jetzt nicht zugänglich): " + describe(it) }
                ?: "Während dieses Tests noch kein zugängliches DEGIRO-Fenster. PIN-Bedienbarkeit ungeklärt."
            return
        }
        val fields = mutableListOf<PinProbePolicy.Field>()
        val keys = mutableListOf<PinKeypadPolicy.Key>()
        val symbols = mutableListOf<PinSymbolProbe.Node>()
        val symbolNodes = mutableListOf<AccessibilityNodeInfo>()
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
            val bounds = android.graphics.Rect()
            node.getBoundsInScreen(bounds)
            val symbolDigit = if (node.childCount == 0 && node.isEnabled)
                PinKeypadPolicy.digit(node.text) ?: PinKeypadPolicy.digit(node.contentDescription) else null
            symbols += PinSymbolProbe.Node(bounds.exactCenterX(), bounds.exactCenterY(),
                bounds.width().toFloat(), bounds.height().toFloat(), symbolDigit,
                !node.text.isNullOrBlank() || !node.contentDescription.isNullOrBlank(), clickable,
                node.isEnabled, node.isClickable,
                node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK },
                parentOwner != null && depth - ownerDepth in 1..2)
            if (exercise != null || login != null) symbolNodes += AccessibilityNodeInfo.obtain(node)
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
        var symbolObservation: PinSymbolProbe.Observation? = null
        val outcome = runCatching { visit(root, 0)
            val structural = PinProbePolicy.classify(fields, complete)
            if (structural == PinProbePolicy.Result.NO_INPUT)
                PinLoginEvidence.classify(PinKeypadPolicy.classify(keys) ?: structural,
                    loginHelp, setup, resetEvidence.count()).let {
                    if (it == PinProbePolicy.Result.LOGIN_RESET_UNCONFIRMED) {
                        val reset = resetEvidence.diagnosis()
                        if (reset == PinProbePolicy.Result.LOGIN_DELETE_LABEL_UNRECOGNIZED)
                            PinSymbolProbe.observe(symbols).also { symbolObservation = it }.result else reset
                    } else it
                } else structural }
            .getOrDefault(PinProbePolicy.Result.INCOMPLETE)
        history.observe(outcome, symbolObservation?.takeIf { it.result == outcome }?.flags)
        message = describe(outcome)
        try {
            val now = SystemClock.elapsedRealtime()
            val candidate = symbolObservation?.candidateIndex
            val zero = symbols.indexOfFirst { it.digit == 0 }
            val eligible = (exercise != null || login != null) && outcome == PinProbePolicy.Result.SYMBOL_DISABLED &&
                now + (if (login != null) 23_000 else 15_000) < deadline && candidate != null && zero >= 0 &&
                symbols.size == symbolNodes.size &&
                symbolObservation?.flags?.let { !it.labelled && it.clickableFlag && it.clickAction && !it.nearbyParentAction } == true
            if (eligible && candidate != null) {
                val signature = root.windowId to (symbols.filter { it.digit != null }.sortedBy { it.digit } + symbols[candidate])
                if (exerciseLayout.observe(signature, now)) {
                    if (login != null) {
                        val digits = (0..9).map { digit -> symbolNodes[symbols.indexOfFirst { it.digit == digit }] }
                        login?.begin(root, digits)
                        if (!loginArmed) exerciseLayout.clear()
                        message = login?.message.orEmpty()
                        if (login?.done == true) { finished = true; stop(message) }
                    } else {
                        exercise?.begin(root, symbolNodes[zero], symbolNodes[candidate])
                        if (!exerciseArmed) exerciseLayout.clear()
                        message = exercise?.message.orEmpty()
                        if (exercise?.done == true) { finished = true; stop(message); onTimeout?.invoke() }
                    }
                } else message = "Warte auf eine unveränderte PIN-Tastatur (mindestens zwei Sekunden). Noch keine Eingabe ausgelöst."
            } else exerciseLayout.clear()
        } finally { symbolNodes.forEach { it.recycle() } }
    }
    private fun describe(outcome: PinProbePolicy.Result): String = when (outcome) {
            PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED -> "Ziffernraster nicht eindeutig; Symbolbereich nicht geprüft."
            PinProbePolicy.Result.SYMBOL_NODE_UNAVAILABLE -> "Im Bereich rechts neben Null kein passendes zugängliches Element. Löschfunktion ungeklärt."
            PinProbePolicy.Result.SYMBOL_NODES_MULTIPLE -> "Im Bereich rechts neben Null mehrere Elemente; Löschfunktion ungeklärt."
            PinProbePolicy.Result.SYMBOL_DISABLED -> "Element rechts neben Null ist deaktiviert. Das beweist keine leere PIN-Eingabe."
            PinProbePolicy.Result.SYMBOL_PARENT_ACTION_OBSERVED -> "Element rechts neben Null ohne direkte Aktion; nahes übergeordnetes Element bietet eine Aktion an. Zuordnung und Löschfunktion nicht bestätigt."
            PinProbePolicy.Result.SYMBOL_CLICK_FLAG_ONLY -> "Element rechts neben Null ist als klickbar markiert, bietet aber keine Klickaktion an."
            PinProbePolicy.Result.SYMBOL_ACTION_ONLY -> "Element rechts neben Null bietet eine Klickaktion an, ist aber nicht als klickbar markiert."
            PinProbePolicy.Result.SYMBOL_LABELLED_PASSIVE -> "Beschriftetes Element rechts neben Null ohne direkte Klickmerkmale und ohne nahe übergeordnete Aktion."
            PinProbePolicy.Result.SYMBOL_UNLABELLED_PASSIVE -> "Unbeschriftetes Element rechts neben Null ohne direkte Klickmerkmale und ohne nahe übergeordnete Aktion."
            PinProbePolicy.Result.SYMBOL_NO_ACTION -> "Element rechts neben Null erkannt, aber keine direkte aktive Klickaktion. Löschfunktion ungeklärt."
            PinProbePolicy.Result.SYMBOL_LABELLED_ACTION -> "Beschriftetes Element mit Klickaktion rechts neben Null erkannt; Beschriftung nicht als Löschen erkannt. Keine Taste gedrückt."
            PinProbePolicy.Result.SYMBOL_UNLABELLED_ACTION -> "Unbeschriftetes Element mit Klickaktion rechts neben Null erkannt. Position beweist keine Löschfunktion; keine Taste gedrückt."
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
