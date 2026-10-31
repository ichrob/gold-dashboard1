package ch.bob.degirocompanion

/** Geometry-only observation of the lower-right keypad region. NEVER a click target or login authorization. */
internal object PinSymbolProbe {
    data class Node(val x: Float, val y: Float, val width: Float, val height: Float,
        val digit: Int?, val labelled: Boolean, val action: Boolean)
    fun classify(nodes: List<Node>): PinProbePolicy.Result {
        val digits = nodes.filter { it.digit != null }
        if (digits.size != 10 || digits.map { it.digit }.toSet() != (0..9).toSet())
            return PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED
        fun key(n: Int) = digits.single { it.digit == n }
        val dx = (key(3).x-key(1).x)/2
        val dy = (key(7).y-key(1).y)/2
        if (dx <= 0 || dy <= 0) return PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED
        for (n in 0..9) {
            val col = if(n == 0) 1 else (n-1)%3
            val row = if(n == 0) 3 else (n-1)/3
            if (kotlin.math.abs(key(n).x-(key(1).x+col*dx)) > dx*.2f ||
                kotlin.math.abs(key(n).y-(key(1).y+row*dy)) > dy*.2f)
                return PinProbePolicy.Result.SYMBOL_LAYOUT_UNCONFIRMED
        }
        val matches = nodes.filter { it.digit == null && it.width > 0 && it.height > 0 &&
            it.width <= dx*1.2f && it.height <= dy*1.2f &&
            kotlin.math.abs(it.x-key(3).x) <= dx*.3f &&
            kotlin.math.abs(it.y-key(0).y) <= dy*.3f }
        if (matches.isEmpty()) return PinProbePolicy.Result.SYMBOL_NODE_UNAVAILABLE
        if (matches.size != 1) return PinProbePolicy.Result.SYMBOL_NODES_MULTIPLE
        val node=matches.single()
        return if (!node.action) PinProbePolicy.Result.SYMBOL_NO_ACTION
            else if (node.labelled) PinProbePolicy.Result.SYMBOL_LABELLED_ACTION
            else PinProbePolicy.Result.SYMBOL_UNLABELLED_ACTION
    }
}
