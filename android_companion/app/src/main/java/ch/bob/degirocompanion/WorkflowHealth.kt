package ch.bob.degirocompanion

import android.content.Context
import org.json.JSONObject
import java.time.Instant

/** Technical aggregates only; never store the goal, screen, package or model response here. */
internal object WorkflowHealth {
    fun record(c: Context, state: String, source: String, confirmed: Int, total: Int, reason: String = "NONE") {
        require(state in setOf("STARTED", "SUCCEEDED", "STOPPED"))
        require(source in setOf("NONE", "LOCAL", "CACHE", "AI"))
        require(confirmed in 0..total && total in 0..12)
        require(state != "SUCCEEDED" || total > 0 && confirmed == total)
        val event = JSONObject().put("reason", reason).put("state", state).put("source", source)
            .put("confirmed", confirmed).put("total", total).put("at", Instant.now().toString())
        c.getSharedPreferences("workflow_health", Context.MODE_PRIVATE).edit().putString("event",event.toString()).commit()
        PhoneDiagnostics.queue(c)
    }
    fun diagnostic(c: Context): JSONObject? = runCatching {
        val raw = c.getSharedPreferences("workflow_health", Context.MODE_PRIVATE).getString("event",null) ?: return null
        JSONObject(raw)
    }.getOrNull()
}
