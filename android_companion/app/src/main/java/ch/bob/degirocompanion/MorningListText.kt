package ch.bob.degirocompanion

/** Export product rows only, never the surrounding account or navigation text. */
internal object MorningListText {
    private val ids=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val row=Regex("(?ism)^(?:SG|BNP)\\s+Gold\\b.{1,500}?\\bDE[A-Z0-9]{9}[0-9]\\b\\s*(?:Soci[eé]t[eé]\\s+G[eé]n[eé]rale\\s+OTC|BNP\\s+(?:Paribas\\s+)?OTC)\\s+(?:EUR|CHF)\\b")
    /** Text fragments may be visited in column order rather than screen order.
     * Reassemble only actual safe leaf-node text at its observed position. No
     * optical correction, inferred identity, currency or numeric value is used.
     * Caller captures this independently before/after the window screenshot. */
    data class Positioned(val node:Int,val line:MorningOcrLayout.Line)
    fun capturePositioned(nodes:List<MorningReadPolicy.Node>,parts:List<Positioned>,
                          expected:List<String>):List<String>? {
        if(nodes.size>500 || parts.isEmpty() || parts.size>300 || expected.isEmpty() || expected.size>10 ||
            expected.distinct()!=expected || expected.any { !SeriesEvidence.validIsin(it) } ||
            MorningReadPolicy.captureGoldList(nodes,true).let { it.kind!=MorningReadPolicy.Kind.COLLECT || it.isins!=expected })return null
        if(parts.map { it.node }.distinct().size!=parts.size)return null
        for(part in parts) {
            val n=nodes.getOrNull(part.node) ?: return null
            if(n.editable || n.containsInput || n.password || n.sensitive || !n.enabled ||
                n.text!=part.line.text || n.text.isBlank())return null
        }
        val lines=parts.map { it.line }
        if(lines.indices.any { a -> (a+1 until lines.size).any { b ->
            val x=lines[a];val y=lines[b]
            maxOf(x.left,y.left)<minOf(x.right,y.right) && maxOf(x.top,y.top)<minOf(x.bottom,y.bottom)
        } })return null
        val text=MorningOcrLayout.readingOrder(lines) ?: return null
        return MorningLocalOcr.productRows(text,expected)
    }

    fun capture(nodes:List<MorningReadPolicy.Node>, expected:List<String>):List<String>? {
        if(nodes.size>500 || expected.isEmpty() || expected.size>10 || expected.distinct()!=expected ||
            expected.any { !SeriesEvidence.validIsin(it) } ||
            MorningReadPolicy.captureGoldList(nodes,true).let { it.kind!=MorningReadPolicy.Kind.COLLECT || it.isins!=expected }) return null
        return expected.map { isin ->
            val candidates=nodes.filter { !it.editable && !it.containsInput && !it.password && !it.sensitive }
                // Samsung sometimes exposes all visible products under one
                // aggregate WebView parent while title nodes contain only the
                // ISIN. Extract EACH exact product-labelled row, never account
                // headers, K/V controls or an arbitrary free-text span.
                .flatMap { n -> row.findAll(n.row.trim()).map { it.value }.toList() }
                .map { it.replace(Regex("\\s+")," ").trim() }
                .filter { ids.findAll(it).map { m -> m.value }.toList()==listOf(isin) }
                .distinct()
            if(candidates.size!=1)return null
            candidates.single()
        }
    }
}
