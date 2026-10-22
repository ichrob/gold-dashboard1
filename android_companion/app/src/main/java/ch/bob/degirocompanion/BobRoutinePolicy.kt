package ch.bob.degirocompanion

/**
 * Explicit, closed allowlist for the local Samsung companion.
 *
 * There is deliberately no generic click, shell, accessibility, network,
 * credentials, broker-session or trading operation. A scheduled trigger can
 * only execute the device-local health check, after an in-app opt-in.
 */
internal object BobRoutinePolicy {
    enum class Action { OPEN_BOB, PICK_IMAGES, LOCAL_HEALTH_CHECK }
    enum class Origin { USER_TAP, SCHEDULE }

    fun permits(action: Action, origin: Origin, scheduleApproved: Boolean = false): Boolean =
        when (origin) {
            Origin.USER_TAP -> action == Action.OPEN_BOB ||
                action == Action.PICK_IMAGES || action == Action.LOCAL_HEALTH_CHECK
            Origin.SCHEDULE -> scheduleApproved && action == Action.LOCAL_HEALTH_CHECK
        }
}
