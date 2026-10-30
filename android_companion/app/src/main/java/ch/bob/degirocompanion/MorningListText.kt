package ch.bob.degirocompanion

/** Export product rows only, never the surrounding account or navigation text. */
internal object MorningListText {
    private val ids=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val row=Regex("(?is)^(?:SG|BNP)\\s+Gold\\b.{1,500}?\\bDE[A-Z0-9]{9}[0-9]\\b\\s*(?:Soci[eé]t[eé]\\s+G[eé]n[eé]rale\\s+OTC|BNP\\s+(?:Paribas\\s+)?OTC)\\s+(?:EUR|CHF)\\b")
    fun capture(nodes:List<MorningReadPolicy.Node>, expected:List<String>):List<String>? {
        if(nodes.size>500 || expected.isEmpty() || expected.size>10 || expected.distinct()!=expected ||
            expected.any { !SeriesEvidence.validIsin(it) } ||
            MorningReadPolicy.captureGoldList(nodes,true).let { it.kind!=MorningReadPolicy.Kind.COLLECT || it.isins!=expected }) return null
        return expected.map { isin ->
            val candidates=nodes.filter { !it.editable && !it.containsInput && !it.password && !it.sensitive }
                .mapNotNull { n -> row.find(n.row.trim())?.value }
                .map { it.replace(Regex("\\s+")," ").trim() }
                .filter { ids.findAll(it).map { m -> m.value }.toList()==listOf(isin) }
                .distinct()
            if(candidates.size!=1)return null
            candidates.single()
        }
    }
}
