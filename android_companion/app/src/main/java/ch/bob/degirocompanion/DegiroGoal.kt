package ch.bob.degirocompanion

/** Public owner-supplied goal parameters. Every search/open goal uses the same login prerequisites. */
internal object DegiroGoal {
    fun acceptsQuery(query: String) = query in setOf("Gold", "Silber") || SeriesEvidence.validIsin(query)
    fun productIsin(text: String): String? {
        val normalized = LocalWorkflow.normalize(text).removeSuffix(".")
        val identifiers = Regex("(?<![a-z0-9])[a-z]{2}[a-z0-9]{9}[0-9](?![a-z0-9])").findAll(normalized).toList()
        val match = identifiers.singleOrNull() ?: return null
        val isin = match.value.uppercase()
        if (!SeriesEvidence.validIsin(isin)) return null
        val rest = normalized.removeRange(match.range).replace(":", " ").trim()
        if (rest.isEmpty()) return isin
        val words = rest.split(Regex("\\s+"))
        val allowed = setOf("öffne", "öffnen", "zeige", "anzeigen", "suche", "suchen", "mir", "das", "die", "der", "produkt", "mit", "isin", "in", "bei", "degiro", "bitte")
        return isin.takeIf { words.all { it in allowed } && (words.any { it in setOf("öffne", "öffnen", "zeige", "anzeigen", "suche", "suchen") } || words == listOf("isin")) }
    }
    fun needsProductIsin(text: String): Boolean = Regex("(?:öffne|zeige|suche)(?: mir)? (?:das |ein )?produkt(?: (?:in|bei) degiro)?[.!]?")
        .matches(LocalWorkflow.normalize(text))
}
