package ch.bob.degirocompanion

import android.content.Context
import org.json.JSONObject

/** Stores only locally verified success; old/manual recipes do not qualify as cache hits. */
internal object WorkflowLibrary {
    private fun prefs(c: Context) = c.getSharedPreferences("local_workflows_v1", Context.MODE_PRIVATE)
    fun match(c: Context, app: String, goal: String): Pair<String, String>? {
        if (goal.isBlank()) return null
        return prefs(c).all.entries.sortedBy { it.key }.firstNotNullOfOrNull { (key, raw) ->
            runCatching {
                val d = JSONObject(raw as String)
                if (d.optInt("version") == 1 && d.optLong("verifiedAt") > 0 && d.optString("app") == app &&
                    WorkflowAiPolicy.sameGoal(d.optString("goal"), goal) &&
                    LocalWorkflow.parse(d.getString("commands")) != null)
                    key to d.getString("commands") else null
            }.getOrNull()
        }
    }
    fun failed(c: Context, app: String, goal: String) {
        val key = match(c, app, goal)?.first ?: return
        val p = prefs(c)
        runCatching {
            val d = JSONObject(p.getString(key, "")!!).put("verifiedAt", 0)
            p.edit().putString(key, d.toString()).commit()
        }
    }
    fun record(c: Context, run: WorkflowRun, goal: String, title: String): String {
        if (!WorkflowAiPolicy.verified(run) || goal.isBlank()) return ""
        val p = prefs(c)
        val existing = match(c, run.app, goal)
        val base = title.trim().take(60).ifBlank { goal.take(60) }
        var key = existing?.first ?: base
        if (existing == null && p.contains(key)) key = (1..20).map { base.take(55) + " ($it)" }.firstOrNull { !p.contains(it) }
            ?: return " · Speicher voll"
        if (!p.contains(key) && p.all.size >= 20) return " · erfolgreich, aber 20 Speicherplätze belegt"
        val d = JSONObject().put("version", 1).put("app", run.app).put("goal", goal)
            .put("commands", WorkflowAiPolicy.commands(run.steps)).put("verifiedAt", System.currentTimeMillis())
        return if (p.edit().putString(key, d.toString()).commit()) " · erfolgreich lokal gespeichert: $key" else " · lokales Speichern fehlgeschlagen"
    }
}
