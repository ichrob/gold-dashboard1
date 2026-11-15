package ch.bob.degirocompanion

import android.content.Context

/**
 * Owner can strengthen privacy and operating restrictions independently of
 * mandatory protections. These preferences are never an authorization to
 * bypass device locks, protected pages, credentials, payments or orders.
 */
internal data class WorkflowSecurityPreferences(
    val readOnlyWorkflows: Boolean = false,
    val offlineAiOnly: Boolean = false
)

internal object WorkflowSecuritySettings {
    private const val PREFS = "workflow_security_owner_v1"

    fun load(context: Context): WorkflowSecurityPreferences {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return WorkflowSecurityPreferences(
            readOnlyWorkflows = p.getBoolean("readOnlyWorkflows", false),
            offlineAiOnly = p.getBoolean("offlineAiOnly", false)
        )
    }

    fun save(context: Context, value: WorkflowSecurityPreferences): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean("readOnlyWorkflows", value.readOnlyWorkflows)
            .putBoolean("offlineAiOnly", value.offlineAiOnly)
            .commit()

    fun permitsExecution(pref: WorkflowSecurityPreferences): Boolean = !pref.readOnlyWorkflows
    fun permitsCloud(pref: WorkflowSecurityPreferences): Boolean = !pref.offlineAiOnly
}
