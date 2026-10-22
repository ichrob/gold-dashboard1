package ch.bob.degirocompanion

/**
 * OCR screenshot-series identity helper.
 *
 * A user explicitly shares a small batch of images. One image can show a complete
 * ISIN while a neighboring screenshot only shows prices/venue. The series is an
 * UNVERIFIED USER-GROUPED observation, not independent broker proof.
 * Conflicting plausible identifiers always reject the entire batch.
 */
internal object SeriesEvidence {
    data class Result(
        val isin: String,
        val imageCount: Int,
        val anchorCount: Int,
        val provisional: Boolean
    )

    private val pattern = Regex("(?<![A-Z0-9])DE[A-Z0-9]{10}(?![A-Z0-9])")

    private fun rawCandidates(text: String): List<String> =
        pattern.findAll(text.uppercase())
            .map { it.value }.distinct().take(20).toList()

    private fun normalize(candidate: String): String {
        if (candidate.length != 12 || !candidate.startsWith("DE")) return candidate
        val letters = candidate.toCharArray()
        // First three WKN filler positions of German ISINs are numeric; OCR
        // often renders zeros as capital letter O in thin mobile fonts.
        for (index in 2..4) {
            letters[index] = when (letters[index]) {
                'O', 'Q' -> '0'
                'I', 'L' -> '1'
                else -> letters[index]
            }
        }
        letters[11] = when (letters[11]) {
            'O', 'Q' -> '0'
            'I', 'L' -> '1'
            'S' -> '5'
            'B' -> '8'
            else -> letters[11]
        }
        return String(letters)
    }

    fun validIsin(value: String): Boolean {
        if (!Regex("[A-Z]{2}[A-Z0-9]{9}[0-9]").matches(value)) return false
        val digits = buildString {
            for (c in value) {
                append(if (c in 'A'..'Z') (c.code - 'A'.code + 10).toString() else c.toString())
            }
        }
        var total = 0
        for ((i, c) in digits.reversed().withIndex()) {
            val digit = c.digitToInt() * if (i % 2 == 1) 2 else 1
            total += digit / 10 + digit % 10
        }
        return total % 10 == 0
    }

    fun validCandidates(text: String): Set<String> =
        rawCandidates(text).map(::normalize).filter(::validIsin).toSet()

    private fun visuallySame(a: String, b: String): Boolean {
        if (a.length != 12 || b.length != 12) return false
        val pairs = setOf(
            "0O", "0Q", "1I", "1L", "5S", "8B", "2Z", "6G"
        )
        var differences = 0
        for (i in a.indices) {
            if (a[i] == b[i]) continue
            val combination = "" + a[i] + b[i]
            if (pairs.none { pair -> pair.contains(a[i]) && pair.contains(b[i]) }) return false
            differences++
            if (differences > 2) return false
        }
        return differences > 0
    }

    fun analyze(texts: List<String>): Result? {
        if (texts.isEmpty() || texts.size > 4) return null
        val raw = texts.map(::rawCandidates)
        val accepted = raw.map { list -> list.map(::normalize).filter(::validIsin).toSet() }
        val all = accepted.flatMap { it }.toSet()
        if (all.size != 1) return null
        val anchor = all.single()

        // Even a checksum-invalid OCR token may indicate another product.
        // Do not silently merge a different identifier into the batch.
        for (candidates in raw) {
            if (candidates.any { candidate ->
                val norm = normalize(candidate)
                norm != anchor && !visuallySame(candidate, anchor) &&
                    !visuallySame(norm, anchor)
            }) return null
        }
        val anchors = accepted.count { anchor in it }
        return Result(anchor, texts.size, anchors, anchors != texts.size)
    }
}
