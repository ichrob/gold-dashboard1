package ch.bob.degirocompanion

/** Preserve evidence from the same observed screen; never combine different quote snapshots. */
internal object ProductDraftQuality {
    fun noRegression(previousMissing: Collection<String>, currentMissing: Collection<String>): Boolean =
        previousMissing.containsAll(currentMissing)

    private val fieldLabel = Regex("^([A-Za-zÄÖÜäöü-]+) \\(Anzeige ungeprüft\\): ")
    private val quoteFields = setOf("Geld", "Brief", "Zuletzt")
    private fun fields(draft: String): Set<String> = draft.lineSequence().mapNotNull {
        fieldLabel.find(it)?.groupValues?.get(1)
    }.toSet()

    /** A stronger complete bid/ask pair may replace a lone quote. Otherwise
     * only a strict superset of field names can replace a saved screen draft.
     * This also protects the original display time and exchange venue.
     * Price values and timestamps from separate screens are NEVER merged. */
    fun preferScreen(previous: String, incoming: String): Boolean {
        if (incoming.isBlank()) return false
        if (previous.isBlank()) return true
        val old = fields(previous)
        val next = fields(incoming)
        val oldPair = old.containsAll(setOf("Geld", "Brief"))
        val nextPair = next.containsAll(setOf("Geld", "Brief"))
        if (oldPair != nextPair) return nextPair
        // Do not replace a known quote label with a different, equally
        // incomplete one. A later screen must preserve all recorded labels.
        if (!next.intersect(quoteFields).containsAll(old.intersect(quoteFields))) return false
        return next.containsAll(old) && next.size > old.size
    }
}
