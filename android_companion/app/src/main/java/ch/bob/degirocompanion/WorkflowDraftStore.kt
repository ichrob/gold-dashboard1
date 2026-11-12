package ch.bob.degirocompanion

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Local, bounded, unverified demonstration only. Never a successfully learned route. */
internal object WorkflowDraftStore {
    private fun prefs(context: Context) = context.getSharedPreferences("workflow_demonstration_draft_v1",0)
    fun save(context: Context) {
        val draft = WorkflowService.demonstrationDraft ?: return
        val choices = JSONObject()
        WorkflowService.demonstrationChoices.filterKeys { it in draft.second.indices }.forEach { (index, labels) ->
            choices.put(index.toString(),JSONArray(labels.filter(WorkflowComposer::validText).distinct().take(30)))
        }
        val data = JSONObject().put("app",draft.first).put("commands",WorkflowAiPolicy.commands(draft.second))
            .put("choices",choices).put("error",WorkflowService.demonstrationError.take(300))
        prefs(context).edit().putString("draft",data.toString()).commit()
    }
    fun restore(context: Context) {
        if (WorkflowService.demonstrationDraft != null) return
        runCatching {
            val raw = prefs(context).getString("draft",null) ?: return
            if (raw.length > 150_000) return
            val data = JSONObject(raw)
            val app = data.getString("app")
            if (!LocalWorkflow.allowedApp(app)) return
            val commands = data.getString("commands")
            val steps = if (commands.isBlank()) emptyList() else LocalWorkflow.parse(commands) ?: return
            val choices = data.optJSONObject("choices") ?: JSONObject()
            WorkflowService.demonstrationChoices = steps.indices.associateWith { index ->
                val labels = choices.optJSONArray(index.toString()) ?: JSONArray()
                (0 until minOf(labels.length(),30)).map { labels.optString(it) }.filter(WorkflowComposer::validText).distinct()
            }
            WorkflowService.demonstrationError = data.optString("error").take(300)
            WorkflowService.demonstrationDraft = app to steps
        }
    }
    fun clear(context: Context) {
        prefs(context).edit().remove("draft").commit()
        WorkflowService.demonstrationDraft = null
        WorkflowService.demonstrationChoices = emptyMap()
        WorkflowService.demonstrationError = ""
    }
}
