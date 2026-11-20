package ch.bob.degirocompanion

/** Strictly local RESEARCH-ONLY recovery for an owner-started Gold list whose
 * enhanced server validation rejected exactly one of ten complete rows.
 * Only actual locally observed valid ISINs may be researched: Samsung's
 * virtualized list can expose fewer than the nine server-recognized rows.
 * This does not validate a list, price, venue, KO threshold or trade; it never
 * uploads this unconfirmed list as a signed broker source. */
internal object ProvisionalIsinReadPolicy {
    fun candidates(
        local: List<String>,
        serverBatchMatches: Boolean,
        stage: String,
        error: String,
        enhanced: Boolean,
        recognized: Int,
        expected: Int,
        images: Int,
        conflicts: Int
    ): List<String>? {
        if(!serverBatchMatches || stage!="read-failed" || error!="ListVerificationError" ||
            !enhanced || recognized!=9 || expected!=10 || images !in 3..4 ||
            conflicts!=0 || local.size !in 1..10 || local.distinct()!=local ||
            local.any { !SeriesEvidence.validIsin(it) }) return null
        return local.toList()
    }
}
