package ch.bob.degirocompanion

/** Changes only an unambiguous value from the owner's last verified workflow. */
internal object WorkflowRevision {
    fun requested(text: String) = Regex("(?i)^(nimm .+ statt .+|wiederhole das(?: mit .+)?)$").matches(text.trim())
    fun apply(text: String, previous: List<WorkflowStep>, chosenIndex: Int? = null): List<WorkflowStep>? {
        val input = text.trim()
        if (input.equals("Wiederhole das", true)) return previous.takeIf { it.isNotEmpty() }
        val replace = Regex("(?i)^nimm (.+) statt (.+)$").matchEntire(input)
        val repeat = Regex("(?i)^wiederhole das mit (.+)$").matchEntire(input)
        val value = (replace?.groupValues?.get(1) ?: repeat?.groupValues?.get(1))?.trim()?.removeSurrounding("\"") ?: return null
        if (!WorkflowComposer.validText(value)) return null
        val candidates = previous.indices.filter { i -> previous[i].action == WorkflowAction.WRITE &&
            (replace == null || LocalWorkflow.normalize(previous[i].value) == LocalWorkflow.normalize(replace.groupValues[2].trim().removeSurrounding("\""))) }
        val target = if (chosenIndex != null) chosenIndex.takeIf { it in candidates } ?: return null else candidates.singleOrNull() ?: return null
        val old = previous[target].value
        // Literal wait checks of the entered value must follow the new value too.
        val changed = previous.mapIndexed { i, step ->
            when {
                i == target -> step.copy(value = value)
                i > target && step.action == WorkflowAction.WAIT && step.target == old -> step.copy(target = value)
                else -> step
            }
        }
        return changed.takeIf { LocalWorkflow.parse(WorkflowAiPolicy.commands(it)) == it }
    }
}
