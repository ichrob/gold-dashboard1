package ch.bob.degirocompanion

/** Explicit, memory-only request. Never survives restart or runs indefinitely. */
internal object ProductReadRequest {
    private var startedAt: Long? = null
    private var lastAttempt: Long? = null
    private var attempts = 0
    fun start(now: Long) { startedAt = now; lastAttempt = null; attempts = 0 }
    fun cancel() { startedAt = null; lastAttempt = null; attempts = 0 }
    fun active(now: Long): Boolean {
        val start = startedAt ?: return false
        if (now < start || now - start >= 60000 || attempts >= 30) { cancel(); return false }
        return true
    }
    fun attempt(now: Long): Boolean {
        if (!active(now)) return false
        val last = lastAttempt
        if (last != null && now - last < 1000) return false
        lastAttempt = now; attempts++
        return true
    }
}
