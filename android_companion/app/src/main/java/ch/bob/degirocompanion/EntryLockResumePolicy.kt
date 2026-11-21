package ch.bob.degirocompanion

/** A local, explicit 15-minute choice, never a screen-lock bypass.
 * A running detail read cannot be reinterpreted as completed by unlocking.
 */
internal object EntryLockResumePolicy {
    fun mayWaitForOwnerUnlock(
        userOptedIn: Boolean,
        entryReadOnly: Boolean,
        sessionActive: Boolean,
        readingInProgress: Boolean,
        productReadOnly: Boolean = false
    ): Boolean = userOptedIn && (entryReadOnly || productReadOnly) &&
        sessionActive && !readingInProgress

    fun mayResume(
        wasWaiting: Boolean,
        sessionActive: Boolean,
        screenInteractive: Boolean,
        keyguardVisible: Boolean,
        deviceLocked: Boolean,
        brokerForeground: Boolean
    ): Boolean = wasWaiting && sessionActive && screenInteractive &&
        !keyguardVisible && !deviceLocked && brokerForeground
}
