package ch.bob.degirocompanion

/**
 * Volatile, explicit one-start bridge between a locally authorized DEGIRO PIN
 * attempt and the existing bounded Gold product reader. Never stores a PIN,
 * account values, screen text, or authorization across process restarts.
 */
internal object LoginToReadHandoff {
    private const val MAX_MILLIS = 65_000L
    private var armedAt = -1L
    fun arm(now: Long) {
        check(armedAt < 0L) { "Anmeldung läuft bereits." }
        armedAt = now
    }
    fun pending(now: Long): Boolean = armedAt >= 0L && now >= armedAt && now - armedAt < MAX_MILLIS
    /** Success means a trusted, stable DEGIRO Markets screen was observed. */
    fun consume(code: String, now: Long): Boolean {
        val allowed = pending(now) && code == "LOCAL_PIN_HOME_VISIBLE"
        clear()
        return allowed
    }
    fun clear() { armedAt = -1L }
}
