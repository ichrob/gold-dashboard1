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
    fun resolve(lines: List<QuoteLayout.Line>, lookup: (String) -> String?): String? {
        val symbols = lines.mapNotNull { headerSymbol(it.text) }.distinct()
        if (symbols.size != 1) return null
        return lookup(symbols.single())?.takeIf { SeriesEvidence.validIsin(it) }
    }
}
