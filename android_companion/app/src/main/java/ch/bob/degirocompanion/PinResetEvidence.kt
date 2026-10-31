package ch.bob.degirocompanion

/** Per-snapshot action ownership. Stores only traversal IDs and structural flags. */
internal class PinResetEvidence {
    private val candidates = mutableSetOf<Int>()
    private val blocked = mutableSetOf<Int>()
    private var enabledLabels = 0
    private var disabledLabels = 0
    fun block(owner: Int?) { if (owner != null) blocked += owner }
    fun observe(owner: Int?, distance: Int, deleteLabel: Boolean, unrelatedLabel: Boolean, enabled: Boolean = true) {
        if (deleteLabel) { if (enabled) enabledLabels++ else disabledLabels++ }
        if (!enabled) { block(owner); return }
        if (owner == null) return
        if (unrelatedLabel) blocked += owner
        if (deleteLabel && distance in 0..2) candidates += owner
    }
    fun count(): Int = (candidates - blocked).size
    fun diagnosis(): PinProbePolicy.Result = when {
        count() == 1 -> PinProbePolicy.Result.LOGIN_DELETE_OFFERED
        count() > 1 -> PinProbePolicy.Result.LOGIN_DELETE_AMBIGUOUS
        candidates.isNotEmpty() -> PinProbePolicy.Result.LOGIN_DELETE_SHARED_TARGET
        enabledLabels > 0 -> PinProbePolicy.Result.LOGIN_DELETE_NO_ACTION
        disabledLabels > 0 -> PinProbePolicy.Result.LOGIN_DELETE_DISABLED
        else -> PinProbePolicy.Result.LOGIN_DELETE_LABEL_UNRECOGNIZED
    }
}
