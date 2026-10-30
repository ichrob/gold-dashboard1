package ch.bob.degirocompanion

/** Device-local DEGIRO identity hints. Never replaces a visible ISIN check. */
internal object ProductSymbolMemory {
    const val CONFLICT = "CONFLICT"
    data class Pairing(val symbol: String, val isin: String)
    private val pair = Regex("^([0-9]{5,12})\\s*\\|\\s*([A-Z]{2}[A-Z0-9]{9}[0-9])$")
    private val label = Regex("(?i)^Symbol\\s*\\|\\s*ISIN$")
    private val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val header = Regex("^([0-9]{5,12})\\s*[•·]\\s*[^|\\n]{2,80}\\s*\\|\\s*[^\\n]{1,12}$")

    fun observe(lines: List<QuoteLayout.Line>, sensitive: Boolean): Pairing? {
        val check = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines, "", sensitive)
        if (check.reason !in setOf(ProductScreenEvidence.Reason.NONE,
                ProductScreenEvidence.Reason.QUOTES_MISSING, ProductScreenEvidence.Reason.CURRENCY_AMBIGUOUS)) return null
        val found = mutableListOf<Pairing>()
        fun add(value: String) {
            val m = pair.matchEntire(value.trim()) ?: return
            if (SeriesEvidence.validIsin(m.groupValues[2])) found += Pairing(m.groupValues[1], m.groupValues[2])
        }
        for (line in lines) {
            val text = line.text.trim()
            if (text.startsWith("Symbol", true)) {
                val prefix = Regex("(?i)^Symbol\\s*\\|\\s*ISIN\\s+").find(text)
                if (prefix != null) add(text.substring(prefix.range.last + 1))
            }
            if (!label.matches(text)) continue
            for (other in lines) if (other.left >= line.right &&
                kotlin.math.abs(other.centerY-line.centerY) <= kotlin.math.max(16,line.height)) add(other.text)
        }
        val only = found.distinct().singleOrNull() ?: return null
        val visible = ids.findAll(lines.joinToString("\n") { it.text.uppercase() }).map { it.value }.toSet()
        return only.takeIf { visible == setOf(it.isin) }
    }

    // Conflicts remain blocked across restarts, rather than silently replacing identity.
    fun merge(previous: String?, observed: String): String = when {
        !SeriesEvidence.validIsin(observed) -> previous ?: CONFLICT
        previous == null || previous == observed -> observed
        else -> CONFLICT
    }
    fun headerSymbol(text: String): String? = header.matchEntire(text.trim())?.groupValues?.get(1)
    // Android may expose the number, venue and status as separate labels.
    // This broader shape is only a scroll-discovery hint, never a stored pairing.
    fun probeHeaderSymbol(text: String): String? {
        headerSymbol(text)?.let { return it }
        val value=text.trim()
        if (Regex("[0-9]{5,12}").matches(value)) return value
        return Regex("(?iu)^([0-9]{5,12})\\s*[•·]\\s*(?:Soci[eé]t[eé] G[eé]n[eé]rale OTC|BNP(?: Paribas)? OTC)(?:\\s*\\|\\s*R)?$")
            .matchEntire(value)?.groupValues?.get(1)
    }
    /** A numeric product header permits identity discovery only, never quote attribution. */
    fun detailSymbol(texts: List<String>): String? {
        if (!texts.any { it.trim().equals("Übersicht", true) || it.trim().equals("Overview", true) }) return null
        if (!texts.any { Regex("(?iu)\\b(gold|xau)\\b").containsMatchIn(it) &&
                Regex("(?iu)\\b(turbo|knock[ -]?out|mini[ -]?(future|long|short))\\b").containsMatchIn(it) }) return null
        val full=texts.mapNotNull { headerSymbol(it) }.distinct()
        val candidates=texts.mapNotNull { probeHeaderSymbol(it) }.distinct()
        if(candidates.size!=1) return null
        if(full.size==1) return full.single()
        // A bare number alone is insufficient even on a derivative overview.
        val venue=Regex("(?iu)^(?:Soci[eé]t[eé] G[eé]n[eé]rale OTC|BNP(?: Paribas)? OTC)(?:\\s*\\|\\s*R)?$")
        val joined=texts.any { it.contains('•') || it.contains('·') }
        return candidates.single().takeIf { texts.any { venue.matches(it.trim()) } ||
            (joined && texts.any { probeHeaderSymbol(it)!=null && !Regex("[0-9]{5,12}").matches(it.trim()) }) }
    }
    fun resolve(lines: List<QuoteLayout.Line>, lookup: (String) -> String?): String? {
        return resolveTexts(lines.map { it.text }, lookup)
    }
    fun resolveTexts(texts: List<String>, lookup: (String) -> String?): String? {
        val symbols = texts.mapNotNull { headerSymbol(it) }.distinct()
        if (symbols.size != 1) return null
        return lookup(symbols.single())?.takeIf { SeriesEvidence.validIsin(it) }
    }
}
