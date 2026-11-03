package ch.bob.degirocompanion

/** Only permits a current, explicit read session to reuse an already-verified
 * daily batch when new image recognition is memory-deferred. The pending
 * evidence stays pending; this policy does not approve trading or orders. */
internal object MorningListFallbackPolicy {
    fun allowed(attempt: Int, pendingBatch: String, earlierBatch: String,
                plan: List<SelectiveDetailPlan.Entry>?): Boolean {
        val exactBatch = Regex("[a-f0-9]{32}")
        return attempt in 18..100 &&
            exactBatch.matches(pendingBatch) &&
            exactBatch.matches(earlierBatch) &&
            earlierBatch != pendingBatch &&
            plan != null && plan.isNotEmpty() && plan.size <= 10 &&
            plan.map { it.isin }.distinct().size == plan.size
    }
}
