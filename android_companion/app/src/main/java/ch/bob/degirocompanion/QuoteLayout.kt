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
    private val venue = Regex("(?i)\\b([A-ZÀ-ÿ]{2,18}\\s+(?:OTC|DOT))\\b")
    private val date = Regex("^(\\d{2}/\\d{2}/20\\d{2}\\s+\\d{2}:\\d{2})$")
    private val heading = Regex("^(?:Handelsplatz|Börse|Venue)\\s*[:：]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val isin = Regex("(?i)\\bDE[A-Z0-9]{10}\\b")

    fun extract(lines: List<Line>): Map<String, String> {
        if (lines.isEmpty()) return emptyMap()
        val results = linkedMapOf<String, String>()
        fun addIfUnique(field: String, candidates: Collection<String>) {
            val distinct = candidates.distinct()
            if (distinct.size == 1) results[field] = distinct.single()
        }
        val sorted = lines.filter { it.text.isNotBlank() }.sortedWith(compareBy(Line::top, Line::left))
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

        val venues = mutableListOf<String>()
        for (line in sorted) {
            val text = line.text.trim()
            val headingMatch = heading.matchEntire(text)
            if (headingMatch != null) {
                venue.find(headingMatch.groupValues[1])?.let { venues += it.groupValues[1].trim() }
                if (headingMatch.groupValues[1].isBlank()) {
                    sorted.filter { other ->
                        other.left > line.right && abs(other.centerY-line.centerY) <= max(16, line.height)
                    }.minByOrNull { it.left }?.let { other ->
                        venue.matchEntire(other.text.trim())?.let { venues += it.groupValues[1] }
                    }
                }
            } else if (isin.containsMatchIn(text)) {
                venue.find(text)?.let { venues += it.groupValues[1].trim() }
            }
        }
        addIfUnique("Handelsplatz", venues.map { it.uppercase().replace(Regex("\\s+"), " ") })

        // This is just what a screenshot displays next to "Zuletzt"; its
        // provenance/timezone is NOT validated, so it never becomes sourceTime.
        val displayedTimes = mutableListOf<String>()
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
        return results
    }
}
