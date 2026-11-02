package ch.bob.degirocompanion

/** Throttle automatic retries of an unchanged, already-deferred local report.
 * Explicit user retries are never throttled. No product fields are inspected. */
internal object DetailAutoRetryPolicy {
    const val DEFERRED_COOLDOWN_MS = 6L * 60 * 60 * 1000
    fun allowed(lastState:String?, lastAt:Long, sameOutbox:Boolean, now:Long):Boolean {
        if(lastState!="DEFERRED" || !sameOutbox) return true
        if(lastAt<=0 || now<lastAt) return true
        return now-lastAt>=DEFERRED_COOLDOWN_MS
    }
}
