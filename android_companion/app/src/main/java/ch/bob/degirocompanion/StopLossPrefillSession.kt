package ch.bob.degirocompanion

/** RAM only, owner-triggered, 120-second broker form draft; never an order permission. */
internal object StopLossPrefillSession {
    private var draft: StopLossPrefillDraft? = null
    private var expiresAt = 0L
    // Optional in-process callback, never persisted or reachable by remote intents.
    var onArmed: (() -> Unit)? = null
    var stage = StopLossPrefillPolicy.Stage.OPEN_FORM
        private set
    var status = "Kein Stop-Loss-Entwurf aktiv."
        private set

    fun arm(value: StopLossPrefillDraft, nowElapsed: Long) {
        draft = value
        expiresAt = nowElapsed + 120_000L
        stage = StopLossPrefillPolicy.Stage.OPEN_FORM
        status = "Entwurf aktiv: DEGIRO-Verkaufsmaske prüfen; niemals Order platzieren."
        onArmed?.invoke()
    }
    fun active(nowElapsed: Long): Boolean {
        if (draft == null) return false
        if (nowElapsed >= expiresAt) { finish("ZEITLIMIT"); return false }
        return true
    }
    fun current(nowElapsed: Long) = if (active(nowElapsed)) draft else null
    fun move(to: StopLossPrefillPolicy.Stage) { stage = to }
    fun finish(code: String) {
        draft = null
        expiresAt = 0L
        stage = StopLossPrefillPolicy.Stage.DONE
        status = when(code) {
            "VORBEREITET" -> "Stop-Loss und Anzahl eingegeben und ausgelesen. NICHT platziert; selbst kontrollieren."
            "USER_STOP" -> "Stop-Loss-Vorbereitung durch Bedienung beendet; bisherige Felder manuell prüfen."
            else -> "Vorbereitung gestoppt: $code. Keine Order ausgelöst; eventuell schon ausgefüllte Felder selbst prüfen."
        }
    }
}
