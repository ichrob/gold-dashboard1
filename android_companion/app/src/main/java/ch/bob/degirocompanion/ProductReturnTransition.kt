package ch.bob.degirocompanion

/** Acknowledged BACK can leave the old accessibility tree visible briefly.
 * Never read/export it under the next target, or bypass a protected view. */
internal class ProductReturnTransition {
    private var target: String? = null
    private var window: Int? = null
    private var started = 0L
    fun begin(previousTarget: String, previousWindow: Int, now: Long) {
        target=previousTarget;window=previousWindow;started=now
    }
    fun waiting(nodes: List<MorningReadPolicy.Node>, currentWindow: Int, now: Long): Boolean {
        val previous=target ?: return false
        if (now < started || now-started >= 5000 || currentWindow != window ||
            !MorningReadPolicy.returnAfterRead(nodes,previous,currentWindow,window,"READ")) {
            clear();return false
        }
        return true
    }
    fun clear() { target=null;window=null;started=0L }
}
