package ch.bob.degirocompanion

/** Only permits a current, explicit read session to reuse an already-verified
 * daily batch when new image recognition is memory-deferred. The pending
 * evidence stays pending; this policy does not approve trading or orders. */
internal object MorningListFallbackPolicy {
    fun allowed(attempt: Int, pendingBatch: String, earlierBatch: String,
                plan: List<SelectiveDetailPlan.Entry>?, resumedSavedCapture: Boolean = false): Boolean {
        val exactBatch = Regex("[a-f0-9]{32}")
        // New captures wait for bounded server OCR before falling back.
        // A previous capture explicitly resumed by the user has already
        // crossed the SERVER's 90-second age gate. It may use that separately
        // confirmed earlier list on the very first receipt.
        return (attempt in 18..100 || resumedSavedCapture && attempt in 0..100) &&
            exactBatch.matches(pendingBatch) &&
            exactBatch.matches(earlierBatch) &&
            earlierBatch != pendingBatch &&
            plan != null && plan.isNotEmpty() && plan.size <= 10 &&
            plan.map { it.isin }.distinct().size == plan.size
    }
}
