package ch.bob.degirocompanion

/** Explicit, memory-only request. Never survives restart or runs indefinitely. */
internal object ProductReadRequest {
    enum class End { STOPPED, TIMEOUT, ATTEMPT_LIMIT, CLOCK_CHANGED }
    var endReason = End.STOPPED
        private set
    var onCancelled: (() -> Unit)? = null
    var onStarted: (() -> Unit)? = null
    private var startedAt: Long? = null
    private var lastAttempt: Long? = null
    private var attempts = 0
    fun start(now: Long) { endReason = End.STOPPED; startedAt = now; lastAttempt = null; attempts = 0; onStarted?.invoke() }
    fun cancel(reason: End = End.STOPPED) { endReason = reason; startedAt = null; lastAttempt = null; attempts = 0; onCancelled?.invoke() }
    fun active(now: Long): Boolean {
        val start = startedAt ?: return false
        val reason = when {
            now < start -> End.CLOCK_CHANGED
            now - start >= 60000 -> End.TIMEOUT
            attempts >= 30 -> End.ATTEMPT_LIMIT
            else -> null
        }
        if (reason != null) { cancel(reason); return false }
        return true
    }
    fun remainingMillis(now: Long): Long {
        if (!active(now)) return 0
        return 60000 - (now - (startedAt ?: return 0))
    }
    fun attempt(now: Long): Boolean {
        if (!active(now)) return false
        val last = lastAttempt
        if (last != null && now - last < 1000) return false
        lastAttempt = now; attempts++
        return true
    }
}
