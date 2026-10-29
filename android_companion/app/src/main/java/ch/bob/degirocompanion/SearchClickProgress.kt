package ch.bob.degirocompanion

/** Memory-only retry state for one semantic search launcher, never coordinates. */
internal class SearchClickProgress {
    private var window = -1
    private var signature = emptyList<Pair<Int, MorningReadPolicy.Node>>()
    private val attempted = mutableSetOf<Int>()
    private var attemptedAt = 0L

    fun clear() {
        window = -1; signature = emptyList(); attempted.clear(); attemptedAt = 0L
    }

    fun select(nodes: List<MorningReadPolicy.Node>, action: MorningReadPolicy.Action,
               windowId: Int, now: Long): MorningReadPolicy.Action {
        if (action.kind != MorningReadPolicy.Kind.SEARCH) { clear(); return action }
        val chain = MorningReadPolicy.searchClickChain(nodes, action)
        val current = chain.map { it to nodes[it] }
        if (window != windowId || signature != current) {
            clear(); window = windowId; signature = current
        }
        if (attempted.isNotEmpty() && now - attemptedAt < 1500)
            return MorningReadPolicy.Action(MorningReadPolicy.Kind.WAIT, code="SEARCH_TRANSITION_PENDING")
        val next = chain.firstOrNull { it !in attempted }
            ?: return MorningReadPolicy.Action(MorningReadPolicy.Kind.WAIT, code="SEARCH_NO_PROGRESS")
        return action.copy(index = next, code = if (attempted.isEmpty()) "" else "SEARCH_RETRY_PARENT")
    }

    /** Android accepting a click is not proof that navigation happened. */
    fun record(index: Int, now: Long) {
        if (signature.any { it.first == index }) { attempted += index; attemptedAt = now }
    }
}
