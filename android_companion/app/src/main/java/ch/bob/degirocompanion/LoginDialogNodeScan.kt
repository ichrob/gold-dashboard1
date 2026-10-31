package ch.bob.degirocompanion

/** Bounded traversal of accessible labels. Never inspect an unsafe node or its descendants. */
internal object LoginDialogNodeScan {
    interface Access<N> {
        fun safe(node: N): Boolean
        fun labels(node: N): List<CharSequence?>
        fun childCount(node: N): Int
        fun child(node: N, index: Int): N?
        fun release(node: N)
    }
    fun <N> collect(root: N, access: Access<N>, interesting: (String) -> Boolean,
        retain: (N) -> Unit): Boolean {
        var visited = 0
        var matched = 0
        fun visit(node: N, depth: Int): Boolean {
            if (++visited > 300 || depth > 25) return false
            if (!access.safe(node)) return true
            if (access.labels(node).any { interesting(LoginDialogPolicy.normalize(it)) }) {
                if (++matched > 80) return false
                retain(node)
            }
            val count = access.childCount(node)
            if (count < 0 || count > 300) return false
            for (index in 0 until count) {
                val child = access.child(node, index) ?: return false
                try { if (!visit(child, depth + 1)) return false }
                finally { access.release(child) }
            }
            return true
        }
        return visit(root, 0)
    }
}
