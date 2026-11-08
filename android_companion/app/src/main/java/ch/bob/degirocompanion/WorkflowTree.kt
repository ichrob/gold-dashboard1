package ch.bob.degirocompanion

/** Fully inspect larger app trees without recursion or executing against a truncated snapshot. */
internal object WorkflowTree {
    const val MAX_NODES = 4096
    const val MAX_DEPTH = 80
    const val MAX_CHILDREN = 1024
    data class Result<T>(val nodes: List<T>, val error: String = "") {
        val complete get() = error.isEmpty()
    }
    fun <T : Any> read(root: T, childCount: (T) -> Int, child: (T, Int) -> T?): Result<T> {
        val nodes = mutableListOf<T>()
        val pending = java.util.ArrayDeque<Pair<T,Int>>()
        pending.addLast(root to 0)
        while (pending.isNotEmpty()) {
            val (node,depth) = pending.removeLast()
            if (depth > MAX_DEPTH) return Result(emptyList(),"DEPTH_LIMIT")
            val count = childCount(node)
            if (count !in 0..MAX_CHILDREN) return Result(emptyList(),"CHILD_LIMIT")
            if (nodes.size + pending.size + 1 + count > MAX_NODES) return Result(emptyList(),"NODE_LIMIT")
            nodes.add(node)
            // Reverse push retains the same preorder as the previous recursive reader.
            for (i in count - 1 downTo 0) {
                val next = child(node,i) ?: return Result(emptyList(),"CHANGED")
                pending.addLast(next to depth + 1)
            }
        }
        return Result(nodes)
    }
    fun explanation(error: String) = when(error) {
        "DEPTH_LIMIT" -> "Ansicht zu tief verschachtelt (mehr als $MAX_DEPTH Ebenen)"
        "CHILD_LIMIT" -> "Ansicht hat zu viele direkte Unterelemente (mehr als $MAX_CHILDREN)"
        "NODE_LIMIT" -> "Ansicht hat mehr als $MAX_NODES Elemente"
        else -> "Ansicht hat sich beim Lesen verändert"
    }
}
