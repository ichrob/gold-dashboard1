package ch.bob.degirocompanion

/** An explicit unlocked read session may bridge the bounded receipt wait.
 * Never wake or unlock the handset; manual stop still releases immediately. */
internal object ListWaitScreenPolicy {
    private const val MAX_WAIT_MS=9L*60*1000
    fun duration(active:Boolean,interactive:Boolean,locked:Boolean):Long =
        if(active && interactive && !locked) MAX_WAIT_MS else 0L
}
