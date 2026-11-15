package ch.bob.degirocompanion

/** One explicit remote gesture per target/window/kind, bounded for the session.
 * Inspect never spends budget or dispatches a gesture. No coordinate storage. */
internal class RemoteGestureBudget {
    private var session = ""
    private val attempted = mutableSetOf<Triple<Int,String,String>>()
    fun clear() { session=""; attempted.clear() }
    fun take(id: String, window: Int, kind: String, query: String): Boolean {
        if(id.isBlank() || window < 0 || kind !in setOf("SEARCH","FOCUS","CATEGORY","RESULT") ||
            (query != "Gold" && !SeriesEvidence.validIsin(query))) return false
        if(session != id) { clear(); session=id }
        if(attempted.size >= 12) return false
        return attempted.add(Triple(window,kind,query))
    }
}
