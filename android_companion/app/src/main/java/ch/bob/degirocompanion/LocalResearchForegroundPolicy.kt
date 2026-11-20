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

    fun mayWait(elapsedMs: Long, sessionActive: Boolean,
                deviceUnlocked: Boolean, brokerVisible: Boolean): Boolean =
        sessionActive && deviceUnlocked && !brokerVisible &&
            elapsedMs in 0 until MAX_WAIT_MS
}
