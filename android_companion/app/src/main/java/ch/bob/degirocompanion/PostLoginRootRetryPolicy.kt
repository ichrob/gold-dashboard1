package ch.bob.degirocompanion

/** Only a transient absent root after a locally verified Markets login may be retried. */
internal object PostLoginRootRetryPolicy {
    private const val MAX_RETRIES = 5
    fun canRetry(attempt: Int): Boolean = attempt in 0 until MAX_RETRIES
}
