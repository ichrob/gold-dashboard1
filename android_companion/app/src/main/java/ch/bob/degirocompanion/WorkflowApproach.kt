package ch.bob.degirocompanion

/** Reuse only verified navigation prefixes in this app. Never replay old input values to reach a new target. */
internal object WorkflowApproach {
    fun prepare(steps: List<WorkflowStep>, frame: WorkflowFrame, routes: List<List<WorkflowStep>>): List<WorkflowStep>? {
        if (steps.isEmpty() || LocalWorkflow.protected(frame)) return null
        val target = steps.first()
        if (target.action == WorkflowAction.WAIT || LocalWorkflow.candidates(target, frame).isNotEmpty()) return steps
        val candidates = routes.flatMap { route ->
            route.indices.filter { LocalWorkflow.normalize(route[it].target) == LocalWorkflow.normalize(target.target) }.flatMap { end ->
                (0 until end).mapNotNull { start ->
                    val prefix = route.subList(start, end)
                    if (prefix.all { it.action == WorkflowAction.CLICK && (it.opensSearch || it.selectsTab || it.expected.isNotBlank()) } &&
                        LocalWorkflow.target(prefix.first(), frame) != null && prefix.size + steps.size <= 12)
                        prefix + steps else null
                }
            }
        }.distinct()
        // Multiple learned ways may mean different screens/accounts: do not choose by chance.
        return candidates.singleOrNull()
    }
}
