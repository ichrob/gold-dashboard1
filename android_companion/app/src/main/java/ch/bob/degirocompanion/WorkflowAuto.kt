package ch.bob.degirocompanion

/** Only a reviewed fixed navigation vocabulary may leave the device automatically. */
internal object WorkflowAuto {
    val labels = setOf("suche", "suchen", "search", "suchbegriff", "suchfeld", "search query", "search field", "filter", "filtern")
    private val ids = setOf("search", "search_src_text", "search_field", "search_input", "search_edit_text", "search_view", "search_button", "search_query", "query", "filter")
    fun context(frame: WorkflowFrame): List<WorkflowNode> {
        if (!LocalWorkflow.allowedApp(frame.app) || LocalWorkflow.protected(frame)) return emptyList()
        return frame.nodes.filter { !it.password }.mapNotNull { n ->
            val label = if (!n.editable && LocalWorkflow.normalize(n.label) in labels) n.label else ""
            val id = if (n.id.substringAfterLast('/').lowercase() in ids && WorkflowAiPolicy.safe(n.id)) n.id else ""
            if ((label.isBlank() && id.isBlank()) || (n.editable && id.isBlank())) null
            else WorkflowNode(label, id, n.editable, n.clickable)
        }.distinct().take(24)
    }
    fun local(goal: String, frame: WorkflowFrame): List<WorkflowStep>? {
        // Explicit commands are owner-authored, not inferred from on-screen text.
        val explicit = LocalWorkflow.parse(goal)
        if (explicit != null && explicit.all { LocalWorkflow.target(it, frame) != null || it.action == WorkflowAction.WAIT })
            return explicit
        val write = Regex("""schreibe (.+?) in (?:das |die |den )?(?:suchfeld|suche|suchbegriff)""", RegexOption.IGNORE_CASE).matchEntire(goal.trim()) ?: return null
        val value = write.groupValues[1].trim().removeSurrounding("\"")
        if (!WorkflowAiPolicy.safe(value)) return null
        val fields = WorkflowSearch.fields(frame)
        if (fields.size > 1) return null
        if (fields.size == 1) return listOf(WorkflowStep(WorkflowAction.WRITE, WorkflowSearch.FIELD, value))
        val button = WorkflowSearch.buttons(frame).singleOrNull() ?: return null
        return listOf(WorkflowStep(WorkflowAction.CLICK, frame.nodes[button].label, opensSearch=true),
            WorkflowStep(WorkflowAction.WRITE, WorkflowSearch.FIELD, value))
    }
    fun autoPlan(goal: String, nodes: List<WorkflowNode>, steps: List<WorkflowStep>): Boolean {
        if (!WorkflowAiPolicy.valid(goal, nodes, steps)) return false
        // A partial navigation proposal must not count as a completed writing goal.
        val writeGoal = Regex("""schreibe (.+?)(?: in .+)?""", RegexOption.IGNORE_CASE).matchEntire(goal.trim())
        val explicit = LocalWorkflow.parse(goal)
        if (writeGoal == null && explicit == null) return false
        if (writeGoal == null && explicit != steps) return false
        if (writeGoal != null) {
            val requested = writeGoal.groupValues[1].trim().removeSurrounding("\"")
            if (steps.lastOrNull { it.action == WorkflowAction.WRITE }?.value != requested) return false
        }
        // Automatically inferred clicks are navigation only. New unobserved targets
        // require the manual reviewed editor; model text cannot enlarge the vocabulary.
        return steps.all { s ->
            when (s.action) {
                WorkflowAction.CLICK -> nodes.any { it.clickable && (s.target == it.id || s.target == it.label) } &&
                    LocalWorkflow.normalize(s.expected) in labels
                WorkflowAction.WRITE -> nodes.any { it.editable && it.id.isNotBlank() && s.target == it.id }
                WorkflowAction.WAIT -> LocalWorkflow.normalize(s.target) in labels || s.target in goal
            }
        }
    }
}

/** Stable-screen detector, bounded even when frames never settle. */
internal class WorkflowAutoObservation(val app: String, val started: Long) {
    var seen = false; private set
    var done = false; private set
    var reason = ""; private set
    private var previous: WorkflowFrame? = null
    private var since = started
    fun stop(why: String) { done = true; reason = why }
    fun next(frame: WorkflowFrame?, now: Long, unlocked: Boolean): WorkflowFrame? {
        if (done) return null
        if (!unlocked) { stop("Bildschirm gesperrt"); return null }
        if (now - started > 20_000) { stop("Kein stabiler, lesbarer Bildschirm erkannt"); return null }
        if (frame == null) return null
        if (frame.app != app) {
            if (seen) stop("Andere App im Vordergrund")
            return null
        }
        seen = true
        if (LocalWorkflow.protected(frame)) { stop("Geschützte Ansicht"); return null }
        if (frame.nodes.isEmpty()) return null
        if (previous != frame) { previous = frame; since = now; return null }
        if (now - since < 1_000) return null
        done = true
        return frame
    }
}
