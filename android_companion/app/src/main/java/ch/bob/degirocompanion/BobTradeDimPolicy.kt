package ch.bob.degirocompanion

/** Owner opt-in for a SCREEN_DIM lease, not a broker-read authorization.
 * It never bypasses Android keyguard or extends a DEGIRO login session.
 */
internal object BobTradeDimPolicy {
    const val MAX_OWNER_MILLIS = 8L * 60 * 60 * 1000
    const val POLL_MILLIS = 25_000L
    const val SCREEN_LEASE_MILLIS = 40_000L

    fun eligible(active: Boolean, ownerElapsed: Long, screenInteractive: Boolean,
                 deviceLocked: Boolean, paired: Boolean, sameTrade: Boolean): Boolean =
        active && ownerElapsed >= 0L && ownerElapsed < MAX_OWNER_MILLIS &&
        screenInteractive && !deviceLocked && paired && sameTrade

    fun validReceipt(state: String, tag: String?, checkedAt: Long, nowSeconds: Long): Boolean =
        state == "ACTIVE" && tag != null && Regex("[a-f0-9]{24}").matches(tag) &&
        checkedAt in (nowSeconds - 60)..(nowSeconds + 20)
}
