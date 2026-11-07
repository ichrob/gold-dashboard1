package ch.bob.degirocompanion

import android.content.Context
import org.json.JSONObject

/** Last result and repeat context stay on the phone; no contents enter diagnostics. */
internal object WorkflowResultStore {
    private fun prefs(c: Context) = c.getSharedPreferences("workflow_result_v1", Context.MODE_PRIVATE)
    fun record(c: Context, run: WorkflowRun, reason: String) {
        val verified = WorkflowAiPolicy.verified(run)
        val json = JSONObject().put("app", run.app).put("confirmed",run.index).put("total",run.steps.size)
            .put("commands", WorkflowAiPolicy.commands(run.steps)).put("success",verified).put("reason",reason.take(500))
            .put("at",System.currentTimeMillis())
        val edit = prefs(c).edit().putString("last",json.toString())
        if (verified) edit.putString("verified",json.toString())
        edit.commit()
    }
    private fun read(c: Context, key: String): JSONObject? { return runCatching { JSONObject(prefs(c).getString(key,null) ?: return null) }.getOrNull() }
    fun previous(c: Context, app: String): List<WorkflowStep>? {
        val result = read(c,"verified") ?: return null
        return if (result.optString("app") == app && result.optBoolean("success")) LocalWorkflow.parse(result.optString("commands")) else null
    }
    fun summary(c: Context): String {
        val j = read(c,"last") ?: return "Noch kein Auftragsergebnis"
        return if (j.optBoolean("success")) "Erledigt · ${j.optInt("confirmed")} Schritte am Bildschirm bestätigt"
            else "Angehalten · ${j.optInt("confirmed")} von ${j.optInt("total")} Schritten bestätigt. ${j.optString("reason")}"
    }
    fun detail(c: Context): String {
        val j = read(c,"last") ?: return summary(c)
        val steps = LocalWorkflow.parse(j.optString("commands")) ?: return summary(c)
        return summary(c) + "\n\n" + steps.mapIndexed { i, step ->
            (if (i < j.optInt("confirmed")) "✓ " else "Offen: ") + when(step.action) {
                WorkflowAction.CLICK -> "${step.target} antippen → ${step.expected}"
                WorkflowAction.WRITE -> "${step.value} in ${step.target} eintragen"
                WorkflowAction.WAIT -> "${step.target} abwarten"
            }
        }.joinToString("\n")
    }
}
