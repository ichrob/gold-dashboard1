package ch.bob.degirocompanion

/** A small isolated wrapper may hold the product prompt beside its input. */
internal object SearchInputCluster {
    private const val PROMPT="Mit Namen, ISIN oder Symbol suchen"
    private fun prompt(s:String)=s.replace(Regex("[\\s\\p{Zs}]+")," ").trim().equals(PROMPT,true)
    fun explicitPrompt(s:String)=prompt(s)
    data class Box(val left:Int,val top:Int,val right:Int,val bottom:Int) {
        fun valid()=left>=0 && top>=0 && right>left && bottom>top
        fun contains(b:Box)=valid() && b.valid() && left<=b.left && top<=b.top && right>=b.right && bottom>=b.bottom
    }
    /** Match only an exact visible prompt contained inside the sole input.
     * No nearest-field or whole-page fallback. All order guards still apply. */
    fun spatial(nodes:List<MorningReadPolicy.Node>, boxes:List<Box>, screen:Box):Set<Int> {
        if(nodes.size!=boxes.size || !screen.valid()) return emptySet()
        val i=nodes.indices.filter { nodes[it].editable }.singleOrNull() ?: return emptySet()
        val input=nodes[i];val box=boxes[i]
        if(!input.enabled || input.password || input.sensitive || !screen.contains(box) ||
            box.bottom.toLong()-box.top>(screen.bottom.toLong()-screen.top)/4) return emptySet()
        val labels=nodes.indices.filter { j ->
            val n=nodes[j]
            !n.password && !n.sensitive && listOf(n.text,n.description,n.hint).any(::prompt) &&
                box.contains(boxes[j])
        }
        return if(labels.isEmpty()) emptySet() else setOf(i)
    }
    fun identify(nodes:List<MorningReadPolicy.Node>):Set<Int> {
        val result=mutableSetOf<Int>()
        fun below(child:Int,parent:Int):Boolean {
            var cursor=child;var count=0
            while(cursor in nodes.indices && count++<nodes.size) {
                if(cursor==parent)return true
                cursor=nodes[cursor].parent
            }
            return false
        }
        for(i in nodes.indices) {
            val input=nodes[i]
            if(!input.editable || input.sensitive || input.password || !input.enabled ||
                listOf(input.text,input.description,input.hint).any { it.isNotBlank() && !prompt(it) }) continue
            var parent=input.parent
            repeat(2) {
                if(parent !in nodes.indices)return@repeat
                val cluster=nodes.indices.filter { below(it,parent) }
                if(cluster.size in 2..8 && cluster.count { nodes[it].editable }==1 &&
                    cluster.none { nodes[it].password || nodes[it].sensitive } &&
                    cluster.flatMap { listOf(nodes[it].text,nodes[it].description,nodes[it].hint) }
                        .filter(String::isNotBlank).let { it.isNotEmpty() && it.all(::prompt) }) result+=i
                parent=nodes[parent].parent
            }
        }
        return result
    }
}
