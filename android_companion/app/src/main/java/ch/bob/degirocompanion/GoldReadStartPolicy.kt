package ch.bob.degirocompanion

/** A user-triggered Gold-list read needs its own verified phone session.
 * The existing gesture and screenshot gates fail closed without it. */
internal object GoldReadStartPolicy {
    enum class Decision { START_SESSION, REUSE_SESSION, BLOCK }
    fun decide(paired: Boolean, sessionActive: Boolean): Decision = when {
        !paired -> Decision.BLOCK
        sessionActive -> Decision.REUSE_SESSION
        else -> Decision.START_SESSION
    }
}
