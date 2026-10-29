package ch.bob.degirocompanion

/** A small isolated wrapper may hold the product prompt beside its input. */
internal object SearchInputCluster {
    private const val PROMPT="Mit Namen, ISIN oder Symbol suchen"
    private fun prompt(s:String)=s.replace(Regex("[\\s\\p{Zs}]+")," ").trim().equals(PROMPT,true)
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
