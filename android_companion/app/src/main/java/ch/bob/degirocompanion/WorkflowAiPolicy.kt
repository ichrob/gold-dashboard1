package ch.bob.degirocompanion

/** Independent device-side checks: a server proposal has no execution authority. */
internal object WorkflowAiPolicy {
    const val CONSENT = "groq-reviewed-text-v1"
    private val privateText = Regex("(?i)(kontostand|account balance|iban|api.?key|bearer|secret|token|@|https?://|\\b[A-Z]{2}\\d{8,}|\\d{6,}|senden|send|publish|veröffentlichen)")
    fun safe(s: String, max: Int = 160, empty: Boolean = false): Boolean =
        s.length <= max && (s.isNotBlank() || empty) && '"' !in s &&
            s.none { it.isISOControl() } && (s.isEmpty() || LocalWorkflow.safeText(s)) && !privateText.containsMatchIn(s)
    fun context(nodes: List<WorkflowNode>): List<WorkflowNode> = nodes.filter { !it.password }.map {
        // Editable text is user content, not a label. Never upload its value.
        WorkflowNode(if (it.editable) "" else it.label, it.id, it.editable, it.clickable)
    }.filter { (it.label.isNotBlank() || it.id.isNotBlank()) && safe(it.label, 120, true) && safe(it.id, 160, true) }.distinct().take(80)
    fun commands(steps: List<WorkflowStep>): String = steps.joinToString("\n") {
        when (it.action) {
            WorkflowAction.CLICK -> if (it.opensSearch) "Öffne Suchfeld über \"" + it.target + "\"" else "Tippe auf \"${it.target}\" -> \"${it.expected}\""
            WorkflowAction.WRITE -> if (it.target == WorkflowSearch.FIELD) "Schreibe \"" + it.value + "\" in das erkannte Suchfeld" else "Schreibe \"${it.value}\" in \"${it.target}\""
            WorkflowAction.WAIT -> "Warte auf \"${it.target}\""
        }
    }
    fun valid(goal: String, nodes: List<WorkflowNode>, steps: List<WorkflowStep>): Boolean {
        if (!safe(goal, 500) || nodes.size !in 1..24 || steps.size !in 1..12) return false
        val known = nodes.flatMap { listOf(it.label, it.id) }.filter { it.isNotBlank() }.toMutableSet()
        for (s in steps) {
            if (s.opensSearch || s.target == WorkflowSearch.FIELD) return false
            if (!safe(s.target) || !safe(s.value, empty=true) || !safe(s.expected, empty=true) || s.target !in known) return false
            when (s.action) {
                WorkflowAction.WRITE -> if (s.value.isEmpty() || s.value !in goal || s.expected.isNotEmpty()) return false
                WorkflowAction.CLICK -> {
                    if (s.value.isNotEmpty() || s.expected.isBlank()) return false
                    known.add(s.expected)
                }
                WorkflowAction.WAIT -> if (s.value.isNotEmpty() || s.expected.isNotEmpty()) return false
            }
        }
        return LocalWorkflow.parse(commands(steps)) == steps
    }
    fun sameGoal(a: String, b: String): Boolean = a.trim() == b.trim()
    fun verified(run: WorkflowRun): Boolean = run.finished && run.steps.isNotEmpty() && run.index == run.steps.size
}
