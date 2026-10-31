package ch.bob.degirocompanion

/** One explicit local exercise. No credentials, retries, login or empty-input inference. */
internal class PinKeypadExercisePolicy {
    enum class Action { NONE, DIGIT, DELETE, FINISH }
    private enum class Stage { NEW, ACTIVE_WAIT, DISABLED_WAIT, DONE, STOPPED }
    private var stage = Stage.NEW
    private var disabledSamples = 0
    val issuedDigit get() = stage != Stage.NEW
    fun begin(confirmedEmpty: Boolean, baselineValid: Boolean): Action {
        if (stage != Stage.NEW || !confirmedEmpty || !baselineValid) return Action.NONE
        stage = Stage.ACTIVE_WAIT // Reserve before dispatch; even a rejected action is never retried.
        return Action.DIGIT
    }
    fun observe(valid: Boolean, enabled: Boolean): Action {
        if (!valid) { stop(); return Action.NONE }
        if (stage == Stage.ACTIVE_WAIT && enabled) {
            stage = Stage.DISABLED_WAIT
            return Action.DELETE
        }
        if (stage == Stage.DISABLED_WAIT) {
            disabledSamples = if (enabled) 0 else disabledSamples + 1
            if (disabledSamples >= 2) { stage = Stage.DONE; return Action.FINISH }
        }
        return Action.NONE
    }
    fun stop() { stage = Stage.STOPPED }
}
