package ch.bob.degirocompanion

/** Memory-only retry state for one semantic search launcher, never coordinates. */
internal class SearchClickProgress {
    private var submitKey: Pair<Int, String>? = null
    private var submitted = false
    private var submitting = false
    private var window = -1
    private var signature = emptyList<MorningReadPolicy.Node>()
    private var currentChain = emptyList<Int>()
    private val attempted = mutableSetOf<Int>()
    private var attemptedAt = 0L

    fun clear() {
        submitKey = null; submitted = false; submitting = false
        window = -1; signature = emptyList(); currentChain = emptyList(); attempted.clear(); attemptedAt = 0L
    }

    fun select(nodes: List<MorningReadPolicy.Node>, action: MorningReadPolicy.Action,
               windowId: Int, now: Long): MorningReadPolicy.Action {
        if (action.kind == MorningReadPolicy.Kind.SUBMIT) {
            val n=nodes.getOrNull(action.index) ?: return MorningReadPolicy.Action(MorningReadPolicy.Kind.BLOCK,code="INVALID_VIEW")
            val key=windowId to n.text
            if(submitKey != key) { clear(); submitKey=key }
            submitting=true
            return if(submitted) action.copy(kind=MorningReadPolicy.Kind.WAIT,index=-1) else action
        }
        if (action.kind != MorningReadPolicy.Kind.SEARCH) { clear(); return action }
        val chain = MorningReadPolicy.searchClickChain(nodes, action)
        // Unrelated live quote rows can shift indices without changing this search.
        val current = chain.map { nodes[it].copy(parent = -1) }
        if (window != windowId || signature != current) {
            clear(); window = windowId; signature = current
        }
        currentChain = chain
        if (attempted.isNotEmpty() && now - attemptedAt < 1500)
            return MorningReadPolicy.Action(MorningReadPolicy.Kind.WAIT, code="SEARCH_TRANSITION_PENDING")
        val next = chain.indices.firstOrNull { it !in attempted }
            ?: return MorningReadPolicy.Action(MorningReadPolicy.Kind.WAIT, code="SEARCH_NO_PROGRESS")
        return action.copy(index = chain[next], code = if (attempted.isEmpty()) "" else "SEARCH_RETRY_PARENT")
    }

    /** Android accepting a click is not proof that navigation happened. */
    fun record(index: Int, now: Long) {
        if(submitting) { submitted=true; return }
        val position = currentChain.indexOf(index)
        if (position >= 0) { attempted += position; attemptedAt = now }
    }
}
