package ch.bob.degirocompanion

/** Owner-named navigation with a verifiable Android selection state. Never infer success from a click acknowledgement. */
internal object WorkflowNavigation {
    fun isTab(label: String) = LocalWorkflow.normalize(label) in setOf("favoriten", "favorites", "watchlist")
    fun selected(step: WorkflowStep, frame: WorkflowFrame): Boolean = isTab(step.target) &&
        frame.nodes.filter { LocalWorkflow.normalize(it.label) == LocalWorkflow.normalize(step.target) || it.id == step.target }
            .singleOrNull()?.let { it.selected && !it.editable && !it.password } == true
}
