package ch.bob.degirocompanion

/** Only a device-authenticated, same-batch synced receipt permits detail upload.
 * Missing old batches are deferred locally, never silently reattached to a new
 * product list or treated as trade/quote verification. */
internal object DetailBatchReceiptPolicy {
    enum class Decision { UPLOAD, DEFER_UNAVAILABLE, RETRY_LATER }

    fun decide(expectedBatch: String, returnedBatch: String, stage: String?): Decision {
        if (!expectedBatch.matches(Regex("[a-f0-9]{32}")) || returnedBatch != expectedBatch)
            return Decision.RETRY_LATER
        return when(stage) {
            "synced", "superseded" -> Decision.UPLOAD
            null -> Decision.DEFER_UNAVAILABLE
            else -> Decision.RETRY_LATER
        }
    }
}
