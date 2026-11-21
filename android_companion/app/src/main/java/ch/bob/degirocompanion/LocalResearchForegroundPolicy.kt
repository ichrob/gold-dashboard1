package ch.bob.degirocompanion

/** The owner's existing, unlocked DEGIRO reading session may outlive the
 * asynchronous OCR receipt. A temporary switch to another foreground app
 * must not consume the bounded *in-DEGIRO* search retries.
 *
 * This is WAIT ONLY: no app launch, screen unlock, input, tap, order or
 * new session. The caller additionally checks the original session ticket.
 */
internal object LocalResearchForegroundPolicy {
    const val MAX_WAIT_MS = 5L * 60L * 1000L
    const val POLL_MS = 1500L
    // A partially virtualized Gold search needs more than eight rapid
    // snapshots. Only wait for the old search input to reappear; do not click.
    const val MAX_VISIBLE_SEARCH_WAIT_MS = 45_000L

    fun mayWaitForVisibleSearch(elapsedMs: Long, sessionActive: Boolean,
                                deviceUnlocked: Boolean, brokerVisible: Boolean,
                                readOnlySearchWait: Boolean): Boolean =
        sessionActive && deviceUnlocked && brokerVisible && readOnlySearchWait &&
            elapsedMs in 0 until MAX_VISIBLE_SEARCH_WAIT_MS

    fun mayWait(elapsedMs: Long, sessionActive: Boolean,
                deviceUnlocked: Boolean, brokerVisible: Boolean): Boolean =
        sessionActive && deviceUnlocked && !brokerVisible &&
            elapsedMs in 0 until MAX_WAIT_MS
}
