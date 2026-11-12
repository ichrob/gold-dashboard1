package ch.bob.degirocompanion

/** Local search semantics; no screen contents are sent to a model. */
internal object WorkflowSearch {
    const val FIELD = "@Suchfeld"
    private val labels = setOf("suche", "suchen", "search", "suchfeld", "suchbegriff", "search query", "search field")
    private val ids = setOf("search", "search_src_text", "search_field", "search_input", "search_edit_text", "search_view", "search_query", "query")
    fun fields(frame: WorkflowFrame): List<Int> = if (LocalWorkflow.protected(frame)) emptyList() else
        frame.nodes.indices.filter { i ->
            val n = frame.nodes[i]
            n.editable && n.id.isNotBlank() && (n.id.substringAfterLast('/').lowercase() in ids ||
                (n.inputValue.isNullOrEmpty() && LocalWorkflow.normalize(n.label) in labels))
        }
    fun buttons(frame: WorkflowFrame): List<Int> = if (LocalWorkflow.protected(frame)) emptyList() else
        frame.nodes.indices.filter { i -> frame.nodes[i].clickable && !frame.nodes[i].editable &&
            LocalWorkflow.normalize(frame.nodes[i].label) in setOf("suche", "suchen", "search") }
    fun safeButton(target: String) = LocalWorkflow.normalize(target) in setOf("suche", "suchen", "search")
}
