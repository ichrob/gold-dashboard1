package ch.bob.degirocompanion

/** Explicitly opted-in, active-trade-only rolling reading sessions.
 * Each server-visible session remains short; local owner consent is bounded
 * by the trade companion's eight-hour safety limit. No order permissions.
 */
internal object TradeReadLeasePolicy {
    const val SEGMENT_MILLIS = 900_000L
    const val RENEW_BEFORE_MILLIS = 45_000L

    fun renew(remainingMillis: Long, tradeVerified: Boolean,
              screenInteractive: Boolean, deviceLocked: Boolean,
              readingInProgress: Boolean): Boolean =
        tradeVerified && screenInteractive && !deviceLocked &&
        !readingInProgress && remainingMillis in 1..RENEW_BEFORE_MILLIS

    fun keepIdleAfterCompletedRead(tradeVerified: Boolean, code: String): Boolean =
        tradeVerified && code in setOf("COMPLETE","COMPLETED")
}
