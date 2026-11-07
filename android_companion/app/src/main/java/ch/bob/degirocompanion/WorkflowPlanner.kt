package ch.bob.degirocompanion

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

internal object WorkflowPlanner {
    fun request(c: Context, app: String, goal: String, nodes: List<WorkflowNode>): Pair<String, List<WorkflowStep>> {
        val id = java.util.UUID.randomUUID().toString().replace("-", "")
        val array = JSONArray()
        nodes.forEach { array.put(JSONObject().put("label", it.label).put("id", it.id).put("editable", it.editable).put("clickable", it.clickable)) }
        val body = JSONObject().put("version",1).put("requestId",id).put("consent",WorkflowAiPolicy.CONSENT)
            .put("app",app).put("goal",goal).put("nodes",array)
        val r = PhoneDiagnostics.workflowPlan(c,body)
        if (r.optString("status") != "proposal") return r.optString("status") to emptyList()
        require(r.getBoolean("ok") && !r.getBoolean("paidFallback") && r.getString("requestId") == id)
        val raw = r.getJSONArray("steps")
        require(raw.length() in 1..12)
        val steps = (0 until raw.length()).map {
            val s = raw.getJSONObject(it)
            require(s.keys().asSequence().toSet() == setOf("action","target","value","expected"))
            listOf("action","target","value","expected").forEach { key -> require(s.get(key) is String) }
            WorkflowStep(WorkflowAction.valueOf(s.getString("action")),s.getString("target"),s.getString("value"),s.getString("expected"))
        }
        require(WorkflowAuto.autoPlan(goal,nodes,steps))
        return "proposal" to steps
    }
    fun error(code: String) = when(code) {
        "setup-required" -> "KI-Zugang fehlt oder ist deaktiviert"
        "daily-limit" -> "KI-Tagesgrenze erreicht"
        "wait-one-minute" -> "KI-Abstand: bitte eine Minute warten"
        "already-requested" -> "KI-Anfrage bereits verarbeitet"
        else -> "Kein sicher automatisch ausführbarer KI-Vorschlag"
    }
}
