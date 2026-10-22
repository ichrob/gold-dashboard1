package ch.bob.degirocompanion

/**
 * Tap-to-speak is the explicit activation: after recognition, ONLY one safe
 * read-only navigation may launch without a second tap. No persistent mic,
 * Android settings, file picker, broker actions or compound chains.
 *
 * Reject the entire plan when not exactly one approved page navigation.
 */
internal object VoiceAutoNavigation {
    fun allowed(plan: PhoneTaskPlan): PhoneTask? {
        if (plan.steps.size != 1) return null
        val task = plan.steps.single()
        return when (task) {
            PhoneTask.OPEN_BOB, PhoneTask.OPEN_MARKET, PhoneTask.OPEN_PRODUCTS,
            PhoneTask.OPEN_LONG_REVIEW, PhoneTask.OPEN_LEVERAGE_REVIEW,
            PhoneTask.OPEN_TRADE,
            PhoneTask.OPEN_SIMULATION, PhoneTask.OPEN_LEARNING,
            PhoneTask.OPEN_RESEARCH -> task
            PhoneTask.OPEN_SETTINGS, PhoneTask.PICK_IMAGES -> null
        }
    }
}
