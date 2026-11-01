package ch.bob.degirocompanion

/** Strict single-screen observation. Never broker permission or an executable quote. */
internal object ProductScreenEvidence {
    const val PACKAGE = "nl.degiro.trader"
    const val HEADER = "BOB APP-LESEENTWURF – NICHT VERIFIZIERT"
    enum class Reason { NONE, OTHER_APP, PROTECTED, TOO_LARGE, LOGIN_OR_ORDER,
        ISIN_MISSING, ISIN_AMBIGUOUS, ISIN_INVALID, CURRENCY_AMBIGUOUS, QUOTES_MISSING, QUOTES_INVALID }
    data class Result(val draft: String = "", val message: String, val reason: Reason = Reason.NONE)
    fun read(packageName: String, lines: List<QuoteLayout.Line>, observedAt: String,
             sensitive: Boolean = false, allowTermsOnly: Boolean = false): Result {
        if (packageName != PACKAGE) return Result(message = "Nur eine sichtbare DEGIRO-Produktseite wird gelesen.", reason = Reason.OTHER_APP)
        if (sensitive) return Result(message = "Eingabe-, Login- oder geschützte Ansicht: nichts übernommen.", reason = Reason.PROTECTED)
        if (lines.size > 500 || lines.sumOf { it.text.length } > 20000)
            return Result(message = "Ansicht zu umfangreich; bitte eine einzelne Produktseite öffnen.", reason = Reason.TOO_LARGE)
        val text = lines.joinToString("\n") { it.text }
        if (Regex("(?i)passwort|password|anmelden|einloggen|login|bestätigungscode|verification code|order platzieren|order bestätigen|place order|confirm order|orderart|ordertyp|order type|limitpreis|limit price|stückzahl|anzahl kaufen").containsMatchIn(text))
            return Result(message = "Login oder Orderansicht erkannt: nichts übernommen.", reason = Reason.LOGIN_OR_ORDER)
        val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(text.uppercase()).map { it.value }.distinct().toList()
        if (ids.isEmpty()) return Result(message = "ISIN fehlt im sichtbaren Ausschnitt. Kurse ohne Produktkennung werden nicht zugeordnet.", reason = Reason.ISIN_MISSING)
        if (ids.size != 1) return Result(message = "Mehrere ISINs sichtbar; bitte ein einzelnes Produkt öffnen.", reason = Reason.ISIN_AMBIGUOUS)
        if (!SeriesEvidence.validIsin(ids.single())) return Result(message = "ISIN-Prüfziffer ungültig; nichts übernommen.", reason = Reason.ISIN_INVALID)
        val currencyPattern = Regex("\\b(EUR|CHF)\\b|€")
        fun currencies(value: String) = currencyPattern.findAll(value.uppercase())
            .map { if (it.value == "€") "EUR" else it.value }.distinct().toList()
        val labels = lines.filter { Regex("(?i)^(Geld|Brief|Zuletzt)\\s*[:：]?$").matches(it.text.trim()) }
        // Currency must belong to a labelled quote, not the account balance above it.
        val quoteCurrencies = lines.flatMap { line ->
            val units = currencies(line.text)
            if (units.isEmpty()) emptyList() else {
                val sample = (labels + line).distinct().map { it.copy(text = it.text.replace("CHF", "EUR")) }
                val quote = QuoteLayout.extract(sample)
                if (quote.keys.any { it in listOf("Geld", "Brief", "Zuletzt") }) units else emptyList()
            }
        }.distinct()
        // Some accessibility trees expose the currency symbol separately from its amount.
        val rowCurrencies = labels.flatMap { label -> lines.filter { other ->
            other.left >= label.right && other.left - label.right <= 540 &&
                kotlin.math.abs(other.centerY - label.centerY) <= kotlin.math.max(16, label.height)
        }.flatMap { currencies(it.text) } }.distinct()
        // QuoteLayout consumes geometry, never arbitrary neighboring text or account data.
        val fields = QuoteLayout.extract(lines.map { it.copy(text = it.text.replace("CHF", "EUR")) })
        val amounts = listOf("Geld", "Brief", "Zuletzt", "Hebel", "KO-Schwelle", "Basispreis", "Bv")
        val selected = fields.filterKeys { it in amounts || it == "Handelsplatz" || it == "Anzeigezeit" }
        val hasQuote = selected.keys.any { it in setOf("Geld", "Brief", "Zuletzt") }
        if (!hasQuote && (!allowTermsOnly || selected.keys.none {
                it in setOf("Hebel", "KO-Schwelle", "Basispreis", "Bv")
            })) return Result(message = "ISIN sichtbar, aber keine eindeutig beschrifteten Kurse zugänglich. Screenshot-Teilen bleibt möglich.", reason = Reason.QUOTES_MISSING)
        // Without quotes, never infer product currency from account balances.
        // Require its explicit identity line or a labelled product-currency row.
        val productCurrency = lines.filter { n ->
            n.text.uppercase().contains(ids.single()) ||
                n.text.trim().lowercase().startsWith("produktwährung:") ||
                n.text.trim().lowercase().startsWith("währung:")
        }.flatMap { currencies(it.text) }.distinct()
        val currency = if (!hasQuote && allowTermsOnly) productCurrency
            else if (quoteCurrencies.isNotEmpty()) quoteCurrencies
            else if (rowCurrencies.isNotEmpty()) rowCurrencies else currencies(text)
        if (currency.size != 1) return Result(message = "Produktwährung nicht eindeutig sichtbar; nichts übernommen.", reason = Reason.CURRENCY_AMBIGUOUS)
        val bid = selected["Geld"]?.replace(',', '.')?.toDoubleOrNull()
        val ask = selected["Brief"]?.replace(',', '.')?.toDoubleOrNull()
        if ((bid != null && bid <= 0) || (ask != null && ask <= 0) || (bid != null && ask != null && bid > ask))
            return Result(message = "Widersprüchliches Kurspaar; nichts übernommen.", reason = Reason.QUOTES_INVALID)
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
