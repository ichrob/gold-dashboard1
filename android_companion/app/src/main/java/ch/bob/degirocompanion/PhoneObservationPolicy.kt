package ch.bob.degirocompanion

/** Specific fixed reasons retain the same stop boundary as generic PROTECTED_VIEW. */
internal object PhoneObservationPolicy {
    fun mustStop(code: String): Boolean = code.startsWith("PROTECTED_") || code in setOf(
        "UNRECOGNIZED_INPUT", "INVALID_VIEW", "SCREEN_LOCKED", "SERVICE_MISSING")
}
