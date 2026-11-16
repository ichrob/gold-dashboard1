package ch.bob.degirocompanion

/** Only running work blocks a new owner start; an idle remote session is replaceable.
 * No secret, screen content or exception message is part of the diagnostic API.
 */
internal object EntryReadStartPolicy {
    enum class Code {
        ENTRY_START_BUSY, ENTRY_START_SERVICE_UNAVAILABLE,
        ENTRY_START_DIAGNOSTICS_UNPAIRED, ENTRY_START_APP_UNAVAILABLE,
        ENTRY_START_KEYPAD_UNVERIFIED, ENTRY_START_DEVICE_LOCKED,
        ENTRY_START_PIN_UNAVAILABLE, ENTRY_START_LOGIN_FAILED,
        ENTRY_START_SESSION_FAILED, ENTRY_START_LAUNCH_FAILED
    }
    fun mayReplaceIdleSession(handoffPending: Boolean, pinRunning: Boolean,
            morningRunning: Boolean, goldRunning: Boolean, productRunning: Boolean) =
        !handoffPending && !pinRunning && !morningRunning && !goldRunning && !productRunning
}
