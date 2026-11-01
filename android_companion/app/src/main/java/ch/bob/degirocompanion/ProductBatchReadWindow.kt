package ch.bob.degirocompanion

/** Preserve only a verified same-window product-read location for the single
 * guarded BACK after a batch observation. FINISHED can reset the reader's
 * anchor before the service records the prior window. */
internal object ProductBatchReadWindow {
    fun keep(previous: Boolean, current: Boolean, finished: Boolean,
             draft: String, expectedIsin: String, sensitive: Boolean,
             unsafe: Boolean): Boolean {
        if (sensitive || unsafe) return false
        if (previous || current) return true
        if (!finished || !SeriesEvidence.validIsin(expectedIsin)) return false
        return draft.lineSequence().any { it == "ISIN: $expectedIsin" }
    }
}
