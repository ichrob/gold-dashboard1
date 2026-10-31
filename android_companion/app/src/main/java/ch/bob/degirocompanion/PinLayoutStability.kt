package ch.bob.degirocompanion

/** Local exact-match samples only; not a tolerance or an authorization to move a click target. */
internal class PinStableObservation<T> {
    private var previous: T? = null
    private var firstAt = 0L
    private var lastAt: Long? = null
    private var samples = 0
    fun clear() { previous = null; lastAt = null; samples = 0 }
    fun observe(value: T?, now: Long): Boolean {
        if (value == null) { clear(); return false }
        val last = lastAt
        if (previous != value || last == null || now <= last || now - last > 1500) {
            previous = value; firstAt = now; samples = 1
        } else samples = (samples + 1).coerceAtMost(3)
        lastAt = now
        return samples >= 3 && now - firstAt >= 2000
    }
}

/** Waits only for the ORIGINAL bounds to return. Never adopts relocated bounds. */
internal class PinBoundsRecovery<T>(private val expected: T, private val deadline: Long) {
    enum class Decision { READY, WAIT, EXPIRED }
    private val stable = PinStableObservation<T>()
    private var expired = false
    var movementPending = false
        private set
    fun observe(actual: T, now: Long): Decision {
        if (actual != expected) { movementPending = true; stable.clear() }
        if (expired || now >= deadline) { expired = true; return Decision.EXPIRED }
        if (actual != expected) return Decision.WAIT
        if (!movementPending) return Decision.READY
        if (!stable.observe(actual, now)) return Decision.WAIT
        movementPending = false
        return Decision.READY
    }
}
