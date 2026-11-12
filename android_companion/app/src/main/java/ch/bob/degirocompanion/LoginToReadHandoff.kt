package ch.bob.degirocompanion

/**
 * Volatile, explicit one-start bridge between a locally authorized DEGIRO PIN
 * attempt and the existing bounded Gold product reader. Never stores a PIN,
 * account values, screen text, or authorization across process restarts.
 */
internal object LoginToReadHandoff {
    private const val MAX_MILLIS = 65_000L
    private var armedAt = -1L
    var searchQuery: String? = null; private set
    var sessionOnly = false; private set
    var freshGold = false; private set
    var generation = 0; private set
    fun arm(now: Long, query: String? = null, sessionOnly: Boolean = false, freshGold: Boolean = false) {
        require(!freshGold || (!sessionOnly && query == null))
        require(!sessionOnly || query == null)
        require(query == null || DegiroGoal.acceptsQuery(query))
        check(armedAt < 0L) { "Anmeldung läuft bereits." }
        this.freshGold = freshGold
        generation++; searchQuery = query; this.sessionOnly = sessionOnly; armedAt = now
    }
    fun pending(now: Long): Boolean = armedAt >= 0L && now >= armedAt && now - armedAt < MAX_MILLIS
    /** Success means a trusted, stable DEGIRO Markets screen was observed. */
    fun consume(code: String, now: Long): Boolean {
        val allowed = pending(now) && code == "LOCAL_PIN_HOME_VISIBLE"
        clear()
        return allowed
    }
    fun clear() { generation++; searchQuery = null; sessionOnly = false; freshGold = false; armedAt = -1L }
}
