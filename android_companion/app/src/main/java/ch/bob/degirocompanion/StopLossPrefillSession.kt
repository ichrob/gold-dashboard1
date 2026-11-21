package ch.bob.degirocompanion

/** RAM-only broker form session. Order authorization is a separate, local, single-use step. */
internal object StopLossPrefillSession {
    private var draft: StopLossPrefillDraft? = null
    private var expiresAt = 0L
    private var armedAt = 0L
    private var submitAttempted = false
    // Optional in-process callback, never persisted or reachable by remote intents.
    var onArmed: (() -> Unit)? = null
    var stage = StopLossPrefillPolicy.Stage.OPEN_FORM
        private set
    var status = "Kein Stop-Loss-Entwurf aktiv."
        private set

    fun arm(value: StopLossPrefillDraft, nowElapsed: Long) {
        draft = value
        expiresAt = nowElapsed + 120_000L
        armedAt = nowElapsed
        submitAttempted = false
        stage = StopLossPrefillPolicy.Stage.OPEN_FORM
        status = "Entwurf aktiv: DEGIRO-Verkaufsmaske vorbereiten; Order erst nach erneuter Freigabe."
        onArmed?.invoke()
    }
    fun active(nowElapsed: Long): Boolean {
        if (draft == null) return false
        if (nowElapsed >= expiresAt) { finish("ZEITLIMIT"); return false }
        return true
    }
    fun current(nowElapsed: Long) = if (active(nowElapsed)) draft else null
    fun waitingForBrokerLaunch(nowElapsed: Long): Boolean =
        active(nowElapsed) && stage in setOf(StopLossPrefillPolicy.Stage.OPEN_FORM,
            StopLossPrefillPolicy.Stage.SUBMIT_ORDER) &&
        nowElapsed >= armedAt && nowElapsed - armedAt < 4_000L
    fun move(to: StopLossPrefillPolicy.Stage) { stage = to }

    /** Form fields were re-read. No order permission yet; owner can inspect DEGIRO. */
    fun readyForOwner(nowElapsed: Long): Boolean {
        if (!active(nowElapsed) || stage != StopLossPrefillPolicy.Stage.VERIFY_QUANTITY) return false
        stage = StopLossPrefillPolicy.Stage.WAIT_OWNER
        status = "Stop-Loss und Anzahl geprüft. In Bob Handy diese EINE Verkaufsorder separat freigeben."
        return true
    }

    /** Approval must come from the non-exported local Activity, never from network. */
    fun canAuthorize(value: StopLossPrefillDraft, nowElapsed: Long): Boolean =
        active(nowElapsed) && stage == StopLossPrefillPolicy.Stage.WAIT_OWNER &&
            !submitAttempted && draft == value

    fun authorizeSubmission(value: StopLossPrefillDraft, nowElapsed: Long): Boolean {
        if (!canAuthorize(value, nowElapsed)) return false
        stage = StopLossPrefillPolicy.Stage.SUBMIT_ORDER
        armedAt = nowElapsed
        status = "Einmaliger Orderauftrag freigegeben. DEGIRO-Felder werden erneut geprüft."
        onArmed?.invoke()
        return true
    }

    /** Consumed BEFORE the irreversible click. A delayed callback cannot replay it. */
    fun takeSubmissionAttempt(nowElapsed: Long): Boolean {
        if (!active(nowElapsed) || submitAttempted ||
            stage != StopLossPrefillPolicy.Stage.SUBMIT_ORDER) return false
        submitAttempted = true
        stage = StopLossPrefillPolicy.Stage.DONE
        return true
    }
    fun finish(code: String) {
        draft = null
        expiresAt = 0L
        armedAt = 0L
        submitAttempted = false
        stage = StopLossPrefillPolicy.Stage.DONE
        status = when(code) {
            "VORBEREITET" -> "Stop-Loss und Anzahl geprüft; noch kein Orderauftrag."
            "ORDER_SENDUNG_UNBESTAETIGT" -> "Einmal auf Order platzieren geklickt. Ob DEGIRO die Order angenommen oder erst eine Bestätigung geöffnet hat, bitte direkt in DEGIRO prüfen."
            "ORDER_BUTTON_ABGELEHNT" -> "Orderknopf nicht ausgelöst. DEGIRO selbst prüfen; keine automatische Wiederholung."
            "USER_STOP" -> "Stop-Loss-Vorbereitung durch Bedienung beendet; bisherige Felder manuell prüfen."
            else -> "Vorgang gestoppt: $code. Keine automatische Wiederholung; DEGIRO auf einen möglicherweise offenen Auftrag prüfen."
        }
    }
}
