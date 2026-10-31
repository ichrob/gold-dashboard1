package ch.bob.degirocompanion

/** Per-snapshot action ownership. Stores only traversal IDs and structural flags. */
internal class PinResetEvidence {
    private val candidates = mutableSetOf<Int>()
    private val blocked = mutableSetOf<Int>()
    fun block(owner: Int?) { if (owner != null) blocked += owner }
    fun observe(owner: Int?, distance: Int, deleteLabel: Boolean, unrelatedLabel: Boolean) {
        if (owner == null) return
        if (unrelatedLabel) blocked += owner
        if (deleteLabel && distance in 0..2) candidates += owner
    }
    fun count(): Int = (candidates - blocked).size
}
