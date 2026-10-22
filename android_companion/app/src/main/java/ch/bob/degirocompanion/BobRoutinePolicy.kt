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

    // Only exact, harmless deep links. No arguments, queries, fragments or arbitrary scripts.
    fun fromLink(raw: String?): Action? = when (raw) {
        "bob-companion://command/open-bob" -> Action.OPEN_BOB
        "bob-companion://command/pick-images" -> Action.PICK_IMAGES
        "bob-companion://command/local-status" -> Action.LOCAL_HEALTH_CHECK
        else -> null
    }

    fun permits(action: Action, origin: Origin, scheduleApproved: Boolean = false): Boolean =
        when (origin) {
            Origin.USER_TAP -> action == Action.OPEN_BOB ||
                action == Action.PICK_IMAGES || action == Action.LOCAL_HEALTH_CHECK
            Origin.SCHEDULE -> scheduleApproved && action == Action.LOCAL_HEALTH_CHECK
        }
}
