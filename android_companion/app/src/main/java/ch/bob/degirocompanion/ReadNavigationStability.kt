package ch.bob.degirocompanion

/** Two observations of the same semantic action, never human-mimic timing. */
internal class ReadNavigationStability {
    private var key = ""
    private var since = -1L
    fun ready(next: String, now: Long): Boolean {
        if (next != key || since < 0L || now < since) {
            key=next;since=now;return false
        }
        return now-since >= 400L
    }
    fun clear() { key="";since=-1L }
}
