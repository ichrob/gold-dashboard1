package ch.bob.degirocompanion

import android.content.Context

/**
 * Owner-selected convenience limits. Not permissions: protected screens, secrets,
 * payment/order blocks, selected-app scope and STOP remain independent.
 */
internal data class WorkflowOwnerLimits(
    val maxSteps: Int = 12,
    val sessionMinutes: Int = 3,
    val stepTimeoutSeconds: Int = 20
) {
    companion object {
        const val MAX_STEPS = 48
        const val MAX_SESSION_MINUTES = 15
        const val MAX_STEP_TIMEOUT_SECONDS = 120

        fun bounded(steps: Int, minutes: Int, seconds: Int) = WorkflowOwnerLimits(
            steps.coerceIn(1, MAX_STEPS),
            minutes.coerceIn(1, MAX_SESSION_MINUTES),
            seconds.coerceIn(10, MAX_STEP_TIMEOUT_SECONDS)
        )
    }
    val sessionMs: Long get() = sessionMinutes * 60_000L
    val stepTimeoutMs: Long get() = stepTimeoutSeconds * 1_000L
}

/** Private, on-device settings; never read from remote instructions or screenshots. */
internal object WorkflowOwnerSettings {
    private const val PREFS = "workflow_owner_limits_v1"
    fun load(context: Context): WorkflowOwnerLimits {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return WorkflowOwnerLimits.bounded(
            prefs.getInt("steps", 12),
            prefs.getInt("minutes", 3),
            prefs.getInt("stepSeconds", 20)
        )
    }
    fun save(context: Context, limits: WorkflowOwnerLimits): Boolean {
        val safe = WorkflowOwnerLimits.bounded(limits.maxSteps, limits.sessionMinutes, limits.stepTimeoutSeconds)
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putInt("steps", safe.maxSteps)
            .putInt("minutes", safe.sessionMinutes)
            .putInt("stepSeconds", safe.stepTimeoutSeconds)
            .commit()
    }
}
