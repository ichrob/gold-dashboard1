package ch.bob.degirocompanion

/** Track the product window after a successful direct read resets its state. */
internal object ProductReadReturnEvidence {
    fun confirmed(before: Boolean, after: Boolean, step: ProductPageReader.Step,
                  ids: Set<String>, target: String, sensitive: Boolean): Boolean {
        if (sensitive || !SeriesEvidence.validIsin(target) ||
            step.cause in setOf(ProductPageReader.Cause.UNSAFE_VIEW,
                ProductPageReader.Cause.IDENTITY_CHANGED,
                ProductPageReader.Cause.INVALID_QUOTES) ||
            step.move == ProductPageReader.Move.ABORT) return false
        if (before || after) return true
        if (step.move != ProductPageReader.Move.FINISHED ||
            ids != setOf(target) || step.result.draft.isBlank()) return false
        val rows=step.result.draft.lineSequence().map(String::trim)
            .filter { it.startsWith("ISIN: ") }.toList()
        return rows == listOf("ISIN: $target") &&
            step.result.draft.startsWith(ProductScreenEvidence.HEADER)
    }
}
