package ch.bob.degirocompanion

/** Strict single-screen observation. Never broker permission or an executable quote. */
internal object ProductScreenEvidence {
    const val PACKAGE = "nl.degiro.trader"
    const val HEADER = "BOB APP-LESEENTWURF – NICHT VERIFIZIERT"
    data class Result(val draft: String = "", val message: String)
    fun read(packageName: String, lines: List<QuoteLayout.Line>, observedAt: String,
             sensitive: Boolean = false): Result {
        if (packageName != PACKAGE) return Result(message = "Nur eine sichtbare DEGIRO-Produktseite wird gelesen.")
        if (sensitive) return Result(message = "Eingabe-, Login- oder geschützte Ansicht: nichts übernommen.")
        if (lines.size > 500 || lines.sumOf { it.text.length } > 20000)
            return Result(message = "Ansicht zu umfangreich; bitte eine einzelne Produktseite öffnen.")
        val text = lines.joinToString("\n") { it.text }
        if (Regex("(?i)passwort|password|anmelden|einloggen|login|bestätigungscode|verification code|order platzieren|order bestätigen|place order|confirm order|orderart|ordertyp|order type|limitpreis|limit price|stückzahl|anzahl kaufen").containsMatchIn(text))
            return Result(message = "Login oder Orderansicht erkannt: nichts übernommen.")
        val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(text.uppercase()).map { it.value }.distinct().toList()
        if (ids.size != 1 || !SeriesEvidence.validIsin(ids.single()))
            return Result(message = "Keine einzelne gültige ISIN sichtbar. Produktdetails öffnen und erneut lesen.")
        val currency = Regex("\\b(EUR|CHF)\\b|€").findAll(text.uppercase())
            .map { if (it.value == "€") "EUR" else it.value }.distinct().toList()
        if (currency.size != 1) return Result(message = "Produktwährung nicht eindeutig sichtbar; nichts übernommen.")
        // QuoteLayout consumes geometry, never arbitrary neighboring text or account data.
        val fields = QuoteLayout.extract(lines.map { it.copy(text = it.text.replace("CHF", "EUR")) })
        val amounts = listOf("Geld", "Brief", "Zuletzt", "Hebel", "KO-Schwelle")
        val selected = fields.filterKeys { it in amounts || it == "Handelsplatz" || it == "Anzeigezeit" }
        if (selected.keys.none { it == "Geld" || it == "Brief" || it == "Zuletzt" })
            return Result(message = "ISIN sichtbar, aber keine eindeutig beschrifteten Kurse zugänglich. Screenshot-Teilen bleibt möglich.")
        val bid = selected["Geld"]?.replace(',', '.')?.toDoubleOrNull()
        val ask = selected["Brief"]?.replace(',', '.')?.toDoubleOrNull()
        if ((bid != null && bid <= 0) || (ask != null && ask <= 0) || (bid != null && ask != null && bid > ask))
            return Result(message = "Widersprüchliches Kurspaar; nichts übernommen.")
        val warning = when {
            Regex("(?i)nicht handelbar|not tradable|trading suspended").containsMatchIn(text) -> "Handel eingeschränkt"
            Regex("(?i)verzögert|delayed").containsMatchIn(text) -> "Kurse verzögert"
            else -> "Keine Aussage zur Handelbarkeit"
        }
        val draft = buildString {
            appendLine(HEADER)
            appendLine("ISIN: ${ids.single()}")
            appendLine("Quelle: DEGIRO-App")
            appendLine("Erfasst: $observedAt")
            appendLine("Währung (Anzeige ungeprüft): ${currency.single()}")
            for ((key, value) in selected) appendLine("$key (Anzeige ungeprüft): $value")
            appendLine("Hinweis (Anzeige ungeprüft): $warning")
            append("Kein automatischer Handelsnachweis, keine Freigabe, keine Order.")
        }
        return Result(draft, "Einmal gelesen. Erfassungszeit ist keine Kurszeit. Zurück zu Bob Handy, um die Werte zu prüfen.")
    }
}
