package ch.bob.degirocompanion

/** Fixed technical states only. Acceptance is an API return value, never proof of an input effect. */
internal class PinKeypadExerciseTrace {
    enum class Stage { WAITING, DIGIT_REQUESTED, DIGIT_ACCEPTED, DELETE_REQUESTED, DELETE_ACCEPTED }
    enum class Reason {
        NONE, ROOT_MISSING, ROOT_PACKAGE, ROOT_WINDOW, ROOT_HIDDEN, ROOT_PROTECTED,
        TARGET_MISSING, TARGET_REFRESH_FAILED, TARGET_PACKAGE, TARGET_WINDOW, TARGET_HIDDEN,
        TARGET_PROTECTED, TARGET_ACTION_UNAVAILABLE, TARGET_BOUNDS_CHANGED, TARGET_CLASS_CHANGED,
        TARGET_ID_CHANGED, STATE_TIMEOUT, DIGIT_REJECTED, DELETE_REJECTED, EXCEPTION,
        USER_TOUCH, WINDOW_EVENT, SCREEN_LOCKED, ACCESS_DISABLED, SERVICE_STOPPED, STOPPED,
        TIMEOUT, STATE_CYCLE, DIGIT_TOUCH_CANCELLED, DELETE_TOUCH_CANCELLED
    }
    var stage = Stage.WAITING
        private set
    var reason = Reason.NONE
        private set
    fun advance(next: Stage) {
        check(reason == Reason.NONE && next.ordinal == stage.ordinal + 1)
        stage = next
    }
    fun end(value: Reason) {
        require(value != Reason.NONE)
        if (reason == Reason.NONE) reason = value
    }
}


