package ch.bob.degirocompanion

/** A time-boxed owner preference, not a keyguard or broker authorization.
 * No background wake locks, automatic login, or orders.
 */
internal object BobWorkModePolicy {
    const val MAX_READ_MILLIS = 15 * 60 * 1000L
    private const val MINUTE = 60_000L
    private const val CLOCK_TOLERANCE = 2 * MINUTE

    fun duration(hours: Int): Long {
        require(hours == 4 || hours == 8) { "Nur vier oder acht Stunden zulässig." }
        return hours * 60L * MINUTE
    }

    /** elapsedRealtime counts suspend, but resets after reboot. Require both
     * clocks to agree so restart / rollback cannot silently extend consent.
     */
    fun remaining(startWall: Long, startElapsed: Long, hours: Int,
                  nowWall: Long, nowElapsed: Long): Long {
        if(hours != 4 && hours != 8) return 0
        if(startWall <= 0 || startElapsed < 0 || nowWall < startWall || nowElapsed < startElapsed) return 0
        val wallAge = nowWall - startWall
        val elapsedAge = nowElapsed - startElapsed
        if(kotlin.math.abs(wallAge - elapsedAge) > CLOCK_TOLERANCE) return 0
        return (duration(hours) - maxOf(wallAge, elapsedAge)).coerceAtLeast(0)
    }

    fun mayStartRead(modeRemaining: Long, screenInteractive: Boolean,
                     deviceLocked: Boolean): Boolean =
        modeRemaining > 0 && screenInteractive && !deviceLocked

    fun remainingMinutes(remaining: Long): Long =
        if(remaining <= 0) 0 else (remaining + MINUTE - 1) / MINUTE
}
