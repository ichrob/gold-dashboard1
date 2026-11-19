package ch.bob.degirocompanion

/** Specific fixed reasons retain the same stop boundary as generic PROTECTED_VIEW. */
internal object PhoneObservationPolicy {
    /** Local Android Gold reader owns protected-view decisions while its
     * explicit bounded read lease is active. A second, passive remote-poll
     * inspection could otherwise stop on a standalone market order launcher
     * before the local reader classifies the actual screen. This NEVER alters
     * the local protection gates or authorizes remote broker navigation. */
    fun localGoldReaderOwnsUi(goldRun: Boolean, readLease: Boolean,
                              settingsOnly: Boolean, unlockTest: Boolean): Boolean =
        goldRun && readLease && !settingsOnly && !unlockTest

    fun mustStop(code: String): Boolean = code.startsWith("PROTECTED_") || code in setOf(
        "UNRECOGNIZED_INPUT", "INVALID_VIEW", "SCREEN_LOCKED", "SERVICE_MISSING")
}
