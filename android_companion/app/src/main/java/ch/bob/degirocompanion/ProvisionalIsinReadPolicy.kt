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

    /** Memory exhaustion is not a validated broker list. After bounded server
     * polling, the owner may still inspect exactly ten ISINs actually observed
     * on this device in the same fresh session. No list/price/trade approval. */
    fun memoryCandidates(
        local: List<String>,
        currentBatch: String,
        receiptBatch: String,
        stage: String,
        error: String,
        images: Int,
        resumedSavedCapture: Boolean
    ): List<String>? {
        if (resumedSavedCapture || !currentBatch.matches(Regex("[a-f0-9]{32}")) ||
            receiptBatch != currentBatch ||
            !((stage == "read-failed" && error == "MemoryError") ||
              (stage == "waiting-memory" && error.isEmpty())) ||
            images !in 3..4 ||
            local.size != 10 || local.distinct().size != local.size ||
            local.any { !SeriesEvidence.validIsin(it) }) return null
        return local.toList()
    }
}
