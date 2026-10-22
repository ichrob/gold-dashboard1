package ch.bob.degirocompanion

/**
 * Single-use local approval. No approval survives a change, cancellation,
 * leaving the app or its short time window. No task content is persisted.
 *
 * [nowMs] must be a monotonic clock such as SystemClock.elapsedRealtime().
 */
internal class PhoneTaskApproval(private val ttlMs: Long = 60_000L) {
    private var approved: PhoneTask? = null
    private var approvedAt: Long = 0L

    fun approve(task: PhoneTask, nowMs: Long) {
        clear()
        approved = task
        approvedAt = nowMs
    }

    fun consume(task: PhoneTask?, nowMs: Long): Boolean {
        val valid = task != null && task == approved &&
            nowMs >= approvedAt && nowMs - approvedAt < ttlMs
        clear() // Always consume, including failed/replayed attempts.
        return valid
    }

    fun clear() {
        approved = null
        approvedAt = 0L
    }
}
