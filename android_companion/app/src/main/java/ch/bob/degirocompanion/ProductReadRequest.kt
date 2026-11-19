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
    private var durationMillis = 60000L
    private var attemptLimit = 30
    /** The ordinary product-read budget stays unchanged. A locally started
     * Gold-list run may select a finite 120-second / 60-attempt budget, always
     * inside the owner's existing unlocked read session. No auto-renewal. */
    fun start(now: Long, maxDurationMillis: Long = 60000L, maxAttempts: Int = 30) {
        require(maxDurationMillis in 1000L..120000L && maxAttempts in 1..60)
        endReason = End.STOPPED; startedAt = now; lastAttempt = null; attempts = 0
        durationMillis = maxDurationMillis; attemptLimit = maxAttempts
        onStarted?.invoke()
    }
    fun cancel(reason: End = End.STOPPED) { endReason = reason; startedAt = null; lastAttempt = null; attempts = 0; onCancelled?.invoke() }
    fun active(now: Long): Boolean {
        val start = startedAt ?: return false
        val reason = when {
            now < start -> End.CLOCK_CHANGED
            now - start >= durationMillis -> End.TIMEOUT
            attempts >= attemptLimit -> End.ATTEMPT_LIMIT
            else -> null
        }
        if (reason != null) { cancel(reason); return false }
        return true
    }
    fun remainingMillis(now: Long): Long {
        if (!active(now)) return 0
        return durationMillis - (now - (startedAt ?: return 0))
    }
    fun attempt(now: Long): Boolean {
        if (!active(now)) return false
        val last = lastAttempt
        if (last != null && now - last < 1000) return false
        lastAttempt = now; attempts++
        return true
    }
}
