package ch.bob.degirocompanion

import android.content.Context
import org.json.JSONObject
import org.json.JSONArray

/** Last result and repeat context stay on the phone; no contents enter diagnostics. */
internal object WorkflowResultStore {
    private fun prefs(c: Context) = c.getSharedPreferences("workflow_result_v1", Context.MODE_PRIVATE)
    fun record(c: Context, run: WorkflowRun, reason: String, request: String = "") {
        val verified = WorkflowAiPolicy.verified(run)
        val json = JSONObject().put("app", run.app).put("confirmed",run.index).put("total",run.steps.size)
            .put("commands", WorkflowAiPolicy.commands(run.steps)).put("success",verified).put("reason",reason.take(500))
            .put("at",System.currentTimeMillis()).put("request",request.ifBlank { WorkflowAiPolicy.commands(run.steps) }.take(5000))
        val items = history(c, "").takeLast(19) + json
        val edit = prefs(c).edit().putString("last",json.toString()).putString("history",JSONArray(items).toString())
        if (verified) edit.putString("verified",json.toString())
        edit.commit()
    }
    private fun read(c: Context, key: String): JSONObject? { return runCatching { JSONObject(prefs(c).getString(key,null) ?: return null) }.getOrNull() }
    fun previous(c: Context, app: String): List<WorkflowStep>? {
        val result = read(c,"verified") ?: return null
        return if (result.optString("app") == app && result.optBoolean("success")) LocalWorkflow.parse(result.optString("commands")) else null
    }
    fun history(c: Context, app: String): List<JSONObject> {
        val items = runCatching {
            val array = JSONArray(prefs(c).getString("history","[]"))
            (0 until array.length()).mapNotNull { array.optJSONObject(it) }
        }.getOrDefault(emptyList()).ifEmpty { listOfNotNull(read(c,"last")) }
        return items.filter { (app.isBlank() || it.optString("app") == app) && LocalWorkflow.parse(it.optString("commands")) != null }.takeLast(20)
    }
    fun summary(c: Context): String = read(c,"last")?.let { summary(it) } ?: "Noch kein Auftragsergebnis"
    fun summary(j: JSONObject): String {
        return if (j.optBoolean("success")) "Erledigt · ${j.optInt("confirmed")} Schritte am Bildschirm bestätigt"
            else "Angehalten · ${j.optInt("confirmed")} von ${j.optInt("total")} Schritten bestätigt. ${j.optString("reason")}"
    }
    fun detail(c: Context): String = read(c,"last")?.let { detail(it) } ?: summary(c)
    fun detail(j: JSONObject): String {
        val steps = LocalWorkflow.parse(j.optString("commands")) ?: return summary(j)
        return summary(j) + "\n\n" + steps.mapIndexed { i, step ->
            (if (i < j.optInt("confirmed")) "✓ " else "Offen: ") + when(step.action) {
                WorkflowAction.CLICK -> "${step.target} antippen → ${step.expected}"
                WorkflowAction.WRITE -> "${step.value} in ${step.target} eintragen"
                WorkflowAction.WAIT -> "${step.target} abwarten"
            }
        }.joinToString("\n")
    }
}
