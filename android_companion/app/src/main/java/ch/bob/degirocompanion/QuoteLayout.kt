package ch.bob.degirocompanion

import kotlin.math.abs
import kotlin.math.max

/**
 * An OCR layout reader for consciously shared product screenshots.
 * Extracts only numbers spatially adjacent to explicit labels. It does not
 * infer executable quotes, broker permission or timestamps from the phone clock.
 * No app/package access or network dependency.
 */
internal object QuoteLayout {
    data class Line(val text: String, val left: Int, val top: Int, val right: Int, val bottom: Int) {
        val centerY: Int get() = (top + bottom) / 2
        val height: Int get() = max(1, bottom - top)
    }

    private val label = Regex("^(Geld|Brief|Zuletzt)\\s*[:：]?$", RegexOption.IGNORE_CASE)
    private val numeric = Regex("^\\s*(?:€\\s*|EUR\\s*)?([0-9]{1,5}[,.][0-9]{2,4})(?:\\s*€|\\s*EUR)?\\s*$", RegexOption.IGNORE_CASE)
    private val inline = Regex("^(Geld|Brief|Zuletzt)\\s*[:：]?\\s*(?:€\\s*|EUR\\s*)?([0-9]{1,5}[,.][0-9]{2,4})(?:\\s*€|\\s*EUR)?\\s*$", RegexOption.IGNORE_CASE)
    private val venue = Regex("(?i)\\b((?:SOCI[EÉ]T[EÉ]\\s+G[EÉ]N[EÉ]RALE|[A-ZÀ-ÿ]{2,18})\\s+(?:OTC|DOT))\\b")
    private val date = Regex("^(\\d{2}/\\d{2}/20\\d{2}\\s+\\d{2}:\\d{2})$")
    private val heading = Regex("^(?:Handelsplatz|Börse|Venue)\\s*[:：]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val isin = Regex("(?i)\\bDE[A-Z0-9]{10}\\b")

    // Read the broker's compact title literally. Bv is an observed notation,
    // not a validated multiplier or a conversion to a product ratio.
    fun productParameters(lines: List<Line>): Map<String, String> {
        val titles = lines.filter { Regex("(?i)\\bGold\\s+(?:Turbo|Knock[ -]?Out\\s+Warrant)\\b").containsMatchIn(it.text) }
        val values = mutableListOf<Map<String, String>>()
        val pattern = Regex("(?i)\\bBAR\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)\\s+BP\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)\\s+Bv\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)(?:\\s+[0-9]{2}/[0-9]{2}/20[0-9]{2})?\\s+LV\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)(?![0-9A-Za-z.,])")
        for (title in titles) {
            val text = lines.filter { it.top >= title.top && it.top <= title.bottom + max(90, title.height * 3) }
                .sortedWith(compareBy(Line::top, Line::left)).joinToString(" ") { it.text }
            for (match in pattern.findAll(text)) {
                val numbers = match.groupValues.drop(1).map { it.replace('.', ',') }
                if (numbers.any { (it.replace(',', '.').toDoubleOrNull() ?: 0.0) <= 0 }) continue
                values += listOf("KO-Schwelle", "Basispreis", "Bv", "Hebel").zip(numbers).toMap()
            }
        }
        // BNP uses different literal labels. Preserve SL/STR and explicit LV;
        // R is not silently converted to the SG Bv notation or an inferred leverage.
        val bnpTitles = lines.filter { Regex("(?i)^BNP\\s+GOLD\\s+Mini\\s+(?:Long|Short)\\b").containsMatchIn(it.text.trim()) }
        val bnp = Regex("(?i)\\bSL\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)\\s+STR\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)\\s+R\\s+[0-9]{1,5}(?:[.,][0-9]{1,4})?(?![0-9A-Za-z.,])")
        for (title in bnpTitles) {
            val text = lines.filter { it.top >= title.top && it.top <= title.bottom + max(90, title.height * 3) }
                .sortedWith(compareBy(Line::top, Line::left)).joinToString(" ") { it.text }
            for (match in bnp.findAll(text)) {
                val numbers = match.groupValues.drop(1).map { it.replace('.', ',') }
                if (numbers.any { (it.replace(',', '.').toDoubleOrNull() ?: 0.0) <= 0 }) continue
                val fields = listOf("KO-Schwelle", "Basispreis").zip(numbers).toMap().toMutableMap()
                val leverage = Regex("(?i)^\\s+LV\\s+([0-9]{1,5}(?:[.,][0-9]{1,4})?)(?![0-9A-Za-z.,])")
                    .find(text.substring(match.range.last + 1))?.groupValues?.get(1)
                if (leverage != null && (leverage.replace(',', '.').toDoubleOrNull() ?: 0.0) > 0)
                    fields["Hebel"] = leverage.replace('.', ',')
                values += fields
            }
        }
        return values.distinct().singleOrNull() ?: emptyMap()
    }

    fun extract(lines: List<Line>): Map<String, String> {
        if (lines.isEmpty()) return emptyMap()
        val results = linkedMapOf<String, String>()
        fun addIfUnique(field: String, candidates: Collection<String>) {
            val distinct = candidates.distinct()
            if (distinct.size == 1) results[field] = distinct.single()
        }
        val fullRow = Regex("(?i)^(?:(?:Geld|Brief|Zuletzt)\\s*[:：]?\\s*(?:€|EUR|CHF)?\\s*[0-9]{1,5}[,.][0-9]{2,4}(?:\\s*(?:€|EUR|CHF))?\\s*)+(?:[0-9]{2}/[0-9]{2}/20[0-9]{2}\\s+[0-9]{2}:[0-9]{2})?$")
        val rowField = Regex("(?i)(Geld|Brief|Zuletzt)\\s*[:：]?\\s*(?:€|EUR|CHF)?\\s*([0-9]{1,5}[,.][0-9]{2,4})(?:\\s*(?:€|EUR|CHF))?")
        val inlineTimes = mutableListOf<String>()
        val expanded = lines.flatMap { line ->
            val texts = line.text.lineSequence().map { it.trim() }.toList()
            val rows = texts.filter { fullRow.matches(it) }
            if (rows.isEmpty()) listOf(line) else listOf(line) + rows.flatMap { row ->
                if (row.startsWith("Zuletzt", true))
                    Regex("[0-9]{2}/[0-9]{2}/20[0-9]{2}\\s+[0-9]{2}:[0-9]{2}$").find(row)?.let { inlineTimes += it.value }
                rowField.findAll(row).map { match ->
                    line.copy(text = match.groupValues[1] + " " + match.groupValues[2])
                }.toList()
            }
        }
        val sorted = expanded.filter { it.text.isNotBlank() }.sortedWith(compareBy(Line::top, Line::left))
        for (field in listOf("Geld", "Brief", "Zuletzt")) {
            val found = mutableListOf<String>()
            for (line in sorted) {
                val text = line.text.trim()
                val oneLine = inline.matchEntire(text)
                if (oneLine != null && oneLine.groupValues[1].equals(field, ignoreCase = true)) {
                    found += oneLine.groupValues[2].replace('.', ',')
                    continue
                }
                val labelMatch = label.matchEntire(text)
                if (labelMatch == null || !labelMatch.groupValues[1].equals(field, ignoreCase = true)) continue
                val nearby = sorted.filter { candidate ->
                    candidate !== line &&
                    candidate.left >= line.right &&
                    candidate.left - line.right <= 540 &&
                    abs(candidate.centerY - line.centerY) <= max(16, line.height) &&
                    numeric.matches(candidate.text.trim())
                }.sortedWith(compareBy<Line> { it.left - line.right }.thenBy { abs(it.centerY - line.centerY) })
                // An adjacent second label on the same row limits the current column.
                val nextLabel = sorted.filter { other ->
                    other !== line && other.left > line.right &&
                    abs(other.centerY-line.centerY) <= max(16,line.height) &&
                    (label.matches(other.text.trim()) || heading.matches(other.text.trim()))
                }.minByOrNull { it.left }
                val value = nearby.firstOrNull { nextLabel == null || it.left < nextLabel.left }
                if (value != null) found += numeric.matchEntire(value.text.trim())!!.groupValues[1].replace('.', ',')
            }
            addIfUnique(field, found)
        }

        // DEGIRO's product header is often split by ML Kit:
        // "DE000PJ9NB98", "•", "BNP", "OTC" are separate word elements.
        // Accept a venue only on the same visual row as a visible ISIN,
        // or next to an explicit "Börse/Handelsplatz" label. Never infer
        // venue merely from the issuer/product name elsewhere on screen.
        val venues = mutableListOf<String>()
        fun sameVisualRow(left: Line, right: Line): Boolean =
            abs(left.centerY - right.centerY) <= max(24, left.height)

        fun addVisibleVenue(value: String) {
            venue.find(value)?.groupValues?.getOrNull(1)?.trim()?.let { venues += it }
        }
        for (anchor in sorted) {
            val text = anchor.text.trim()
            val headingMatch = heading.matchEntire(text)
            val isHeader = isin.containsMatchIn(text)
            if (!isHeader && headingMatch == null) continue

            // Venue explicitly present in the same OCR line.
            if (isHeader) addVisibleVenue(text)
            if (headingMatch != null) addVisibleVenue(headingMatch.groupValues[1])

            // Venue positioned to the right of the ISIN or venue label.
            // OCR often separates the issuer and OTC into distinct elements.
            val neighbors = sorted.filter { other ->
                other !== anchor && sameVisualRow(anchor, other) &&
                other.left >= anchor.right - 12 &&
                other.left - anchor.right <= 460 &&
                other.left >= anchor.left
            }.sortedBy { it.left }

            for (neighbor in neighbors) addVisibleVenue(neighbor.text.trim())

            // Join only locally adjacent word elements, not separate rows.
            // This recovers ["BNP", "OTC"] alongside the recognized ISIN.
            for (index in 0 until neighbors.size - 1) {
                val first = neighbors[index]
                val second = neighbors[index + 1]
                if (sameVisualRow(first, second) &&
                    second.left >= first.right - 8 &&
                    second.left - first.right <= 54) {
                    addVisibleVenue(first.text.trim() + " " + second.text.trim())
                }
            }
        }
        addIfUnique("Handelsplatz", venues.map { it.uppercase().replace(Regex("\\s+"), " ") })

        // This is just what a screenshot displays next to "Zuletzt"; its
        // provenance/timezone is NOT validated, so it never becomes sourceTime.
        val displayedTimes = inlineTimes.toMutableList()
        for (line in sorted) {
            if (label.matchEntire(line.text.trim())?.groupValues?.get(1)?.equals("Zuletzt", true) != true) continue
            sorted.filter { other ->
                other.left > line.right &&
                abs(other.centerY-line.centerY) <= max(16,line.height)
            }.forEach { other ->
                date.matchEntire(other.text.trim())?.let { displayedTimes += it.groupValues[1] }
            }
        }
        addIfUnique("Anzeigezeit", displayedTimes)
        results.putAll(productParameters(sorted))
        return results
    }
}
