package ch.bob.degirocompanion

/** A bounded scroll transaction; drafts stay private until the header is rechecked. */
internal class ProductPageReader {
    enum class Move { NONE, FORWARD, BACKWARD, FINISHED, ABORT }
    data class Step(val move: Move, val result: ProductScreenEvidence.Result)
    private var isin: String? = null
    private var window: Int? = null
    private var returning = false
    private var forward = 0
    private var backward = 0
    private var candidate: ProductScreenEvidence.Result? = null
    val anchored get() = isin != null
    fun reset() { isin = null; window = null; returning = false; forward = 0; backward = 0; candidate = null }
    private fun stop(message: String): Step { reset(); return Step(Move.ABORT, ProductScreenEvidence.Result(message = message)) }
    fun scrollFailed(move: Move) {
        if (move == Move.FORWARD) returning = true
        else if (move == Move.BACKWARD) { candidate = null; backward = 8 }
    }
    fun inspect(windowId: Int, lines: List<QuoteLayout.Line>, at: String, sensitive: Boolean,
                canForward: Boolean, canBackward: Boolean): Step {
        val direct = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines, at, sensitive)
        if (direct.reason in setOf(ProductScreenEvidence.Reason.PROTECTED, ProductScreenEvidence.Reason.LOGIN_OR_ORDER,
                ProductScreenEvidence.Reason.TOO_LARGE, ProductScreenEvidence.Reason.ISIN_INVALID,
                ProductScreenEvidence.Reason.ISIN_AMBIGUOUS)) return stop(direct.message)
        val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(lines.joinToString("\n") { it.text.uppercase() }).map { it.value }.distinct().toList()
        if (!anchored) {
            if (ids.size != 1 || !SeriesEvidence.validIsin(ids.single())) return Step(Move.NONE, direct)
            isin = ids.single(); window = windowId
        }
        if (windowId != window || (ids.isNotEmpty() && ids.singleOrNull() != isin)) return stop("Produkt oder Fenster gewechselt. Seitenprüfung abgebrochen.")
        if (returning) {
            if (ids.singleOrNull() == isin) {
                val value = candidate
                reset()
                return if (value != null) Step(Move.FINISHED, value.copy(message = "Produktseite automatisch gelesen und ISIN nach Rückkehr erneut geprüft. Werte bleiben ungeprüfte App-Beobachtungen."))
                else Step(Move.ABORT, ProductScreenEvidence.Result(message = "Seite geprüft, aber kein eindeutig zuordenbarer Kurs gefunden."))
            }
            if (!canBackward || backward >= 8) return stop("Rückprüfung der ISIN nicht möglich. Kein Entwurf übernommen.")
            backward++
            return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "Bob kehrt zur Produktkennung zurück und prüft die Zuordnung."))
        }
        // Identity is carried only within this uninterrupted, same-window scroll transaction.
        val sample = if (ids.isEmpty()) lines + QuoteLayout.Line("ISIN: $isin", -100, -100, -1, -1) else lines
        val observed = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, sample, at, sensitive)
        if (observed.reason == ProductScreenEvidence.Reason.QUOTES_INVALID) return stop(observed.message)
        fun score(value: ProductScreenEvidence.Result) = listOf("Geld (", "Brief (", "Zuletzt (").count { value.draft.contains(it) }
        if (observed.draft.isNotBlank() && (candidate == null || score(observed) >= score(candidate!!))) candidate = observed
        if (canForward) {
            if (forward >= 8) return stop("Scrollgrenze erreicht. Keine vollständige Seitenprüfung; kein Entwurf übernommen.")
            forward++
            return Step(Move.FORWARD, ProductScreenEvidence.Result(message = "Bob liest die Produktseite abschnittsweise. Bitte währenddessen nicht bedienen."))
        }
        returning = true
        return inspect(windowId, lines, at, sensitive, false, canBackward)
    }
}
