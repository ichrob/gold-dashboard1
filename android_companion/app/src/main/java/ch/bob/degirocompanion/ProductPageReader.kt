package ch.bob.degirocompanion

/** A bounded scroll transaction; drafts stay private until the header is rechecked. */
internal class ProductPageReader {
    enum class Move { NONE, FORWARD, BACKWARD, FINISHED, ABORT }
    enum class Cause { NONE, WAIT_PROTECTED, WAIT_IDENTITY, WAIT_SCROLL, UNSAFE_VIEW,
        IDENTITY_CHANGED, NO_QUOTES, RETURN_FAILED, SCROLL_LIMIT, INVALID_QUOTES, SEEK_HEADER, SEEK_LIMIT, WAIT_SCROLL_LAYOUT, SCROLL_LAYOUT_CHANGED, QUOTES_CAPTURED }
    data class Step(val move: Move, val result: ProductScreenEvidence.Result, val cause: Cause = Cause.NONE)
    private var rejectedForward = 0
    private var rejectedBackward = 0
    private var layoutWaits = 0
    private var seekSteps = 0
    private var seekWindow: Int? = null
    private var isin: String? = null
    private var window: Int? = null
    private var returning = false
    private var forward = 0
    private var backward = 0
    private var anchorParameters: Map<String, String> = emptyMap()
    private var candidate: ProductScreenEvidence.Result? = null
    val anchored get() = isin != null
    fun sameWindow(windowId: Int): Boolean = anchored && window == windowId
    fun reset() { rejectedForward = 0; rejectedBackward = 0; layoutWaits = 0; seekSteps = 0; seekWindow = null; isin = null; window = null; returning = false; forward = 0; backward = 0; candidate = null; anchorParameters = emptyMap() }
    private fun stop(message: String, cause: Cause, reason: ProductScreenEvidence.Reason = ProductScreenEvidence.Reason.NONE): Step {
        reset(); return Step(Move.ABORT, ProductScreenEvidence.Result(message = message, reason = reason), cause)
    }
    fun scrollSucceeded(move: Move) {
        if (move == Move.FORWARD) rejectedForward = 0
        else if (move == Move.BACKWARD) rejectedBackward = 0
    }
    fun scrollFailed(move: Move) {
        // A stale accessibility node can reject an action while the page rebuilds.
        // Retry only via a fresh traversal; the existing scroll/time limits apply.
        if (move == Move.FORWARD && ++rejectedForward >= 3) returning = true
        else if (move == Move.BACKWARD && ++rejectedBackward >= 3) {
            candidate = null; backward = 8; if (!anchored) seekSteps = 4
        }
    }
    fun inspect(windowId: Int, lines: List<QuoteLayout.Line>, at: String, sensitive: Boolean,
                canForward: Boolean, canBackward: Boolean, scrollAmbiguous: Boolean = false, requireParameters: Boolean = false, identityHint: String? = null): Step {
        val direct = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines, at, sensitive)
        // Launch/login transitions must not consume an unanchored request. Read nothing
        // from them; only wait within the existing 60-second request budget.
        if (!anchored && direct.reason in setOf(ProductScreenEvidence.Reason.PROTECTED, ProductScreenEvidence.Reason.LOGIN_OR_ORDER))
            return Step(Move.NONE, direct.copy(message = "Geschützte oder Login-Ansicht übersprungen. Bob wartet auf die Produktseite; nichts übernommen."), Cause.WAIT_PROTECTED)
        if (direct.reason in setOf(ProductScreenEvidence.Reason.PROTECTED, ProductScreenEvidence.Reason.LOGIN_OR_ORDER,
                ProductScreenEvidence.Reason.TOO_LARGE, ProductScreenEvidence.Reason.ISIN_INVALID,
                ProductScreenEvidence.Reason.ISIN_AMBIGUOUS)) return stop(direct.message, Cause.UNSAFE_VIEW, direct.reason)
        val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(lines.joinToString("\n") { it.text.uppercase() }).map { it.value }.distinct().toList()
        // Identity changes must be rejected even while the scroll tree is transient.
        if (anchored && (identityHint != null && identityHint != isin || windowId != window || (ids.isNotEmpty() && ids.singleOrNull() != isin)))
            return stop("Produkt oder Fenster gewechselt. Seitenprüfung abgebrochen.", Cause.IDENTITY_CHANGED)
        if (scrollAmbiguous) {
            if (anchored && ++layoutWaits > 5)
                return stop("Scrollbereich nach fünf Nachprüfungen weiterhin uneindeutig. Kein Entwurf übernommen.", Cause.SCROLL_LAYOUT_CHANGED)
            return Step(Move.NONE, direct.copy(draft = "", message = "Seitenaufbau noch nicht eindeutig. Bob wartet innerhalb des 60-Sekunden-Limits auf den Produktbereich."), Cause.WAIT_SCROLL_LAYOUT)
        }
        layoutWaits = 0
        if (!anchored) {
            val anchorIds = if (ids.isEmpty() && identityHint != null && SeriesEvidence.validIsin(identityHint)) listOf(identityHint) else ids
            val visibleText = lines.joinToString("\n") { it.text }
            val quoteSection = Regex("(?i)kursdaten|produktdetails").containsMatchIn(visibleText) &&
                Regex("(?i)\\bGeld\\b").containsMatchIn(visibleText) && Regex("(?i)\\bBrief\\b").containsMatchIn(visibleText)
            if (anchorIds.isEmpty() && quoteSection && canBackward) {
                if (seekWindow != null && seekWindow != windowId) return stop("Fensterwechsel bei der Kopfzeilensuche. Prüfung abgebrochen.", Cause.IDENTITY_CHANGED)
                if (seekSteps >= 4) return stop("Produktkennung nach vier Rückwärtsschritten nicht gefunden. Nichts übernommen.", Cause.SEEK_LIMIT)
                seekWindow = windowId; seekSteps++
                return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "Kursbereich erkannt. Bob scrollt zur Produktkennung; noch keine Werte übernommen."), Cause.SEEK_HEADER)
            }
            if (anchorIds.size != 1 || !SeriesEvidence.validIsin(anchorIds.single())) return Step(Move.NONE, direct, Cause.WAIT_IDENTITY)
            isin = anchorIds.single(); window = windowId
            anchorParameters = QuoteLayout.productParameters(lines)
        }
        if (windowId != window || (ids.isNotEmpty() && ids.singleOrNull() != isin)) return stop("Produkt oder Fenster gewechselt. Seitenprüfung abgebrochen.", Cause.IDENTITY_CHANGED)
        // Informational footers contain no additional quote evidence. Preserve the
        // candidate and return to the original identity within this transaction.
        if (MorningReadPolicy.detailFooter(lines.map { it.text })) returning = true
        if (returning) {
            if (ids.singleOrNull() == isin) {
                // Read compact parameters only after the original ISIN has been
                // rechecked on return. Do not reuse a different page's title.
                val parameters = QuoteLayout.productParameters(lines).ifEmpty { anchorParameters }
                if (requireParameters && parameters.keys.containsAll(listOf("Hebel", "KO-Schwelle", "Basispreis", "Bv")).not() && canBackward && backward < 4) {
                    backward++
                    return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "Bob sucht die fehlenden Produktparameter in der Kopfzeile."))
                }
                val value = candidate?.let { observation ->
                    val extra = parameters.filterKeys { !observation.draft.contains("$it (Anzeige ungeprüft):") }
                        .map { (key, field) -> "$key (Anzeige ungeprüft): $field" }.joinToString("\n")
                    if (extra.isEmpty()) observation else observation.copy(draft = observation.draft + "\n" + extra)
                }
                reset()
                return if (value != null) Step(Move.FINISHED, value.copy(message = "Produktseite automatisch gelesen und ISIN nach Rückkehr erneut geprüft. Werte bleiben ungeprüfte App-Beobachtungen."))
                else Step(Move.ABORT, ProductScreenEvidence.Result(message = "Seite geprüft, aber kein eindeutig zuordenbarer Kurs gefunden."), Cause.NO_QUOTES)
            }
            if (!canBackward || backward >= 8) return stop("Rückprüfung der ISIN nicht möglich. Kein Entwurf übernommen.", Cause.RETURN_FAILED)
            backward++
            return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "Bob kehrt zur Produktkennung zurück und prüft die Zuordnung."))
        }
        // Identity is carried only within this uninterrupted, same-window scroll transaction.
        val sample = if (ids.isEmpty()) lines + QuoteLayout.Line("ISIN: $isin", -100, -100, -1, -1) else lines
        val observed = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, sample, at, sensitive)
        if (observed.reason == ProductScreenEvidence.Reason.QUOTES_INVALID) return stop(observed.message, Cause.INVALID_QUOTES, observed.reason)
        fun score(value: ProductScreenEvidence.Result) = listOf("Geld (", "Brief (", "Zuletzt (").count { value.draft.contains(it) }
        if (observed.draft.isNotBlank() && (candidate == null || score(observed) >= score(candidate!!))) candidate = observed
        // A complete labelled quote pair is the useful end of this read. Avoid
        // scrolling through unrelated footer sections or probing the page bottom.
        // Publication still requires returning to the original visible ISIN.
        if (observed.draft.contains("Geld (") && observed.draft.contains("Brief (")) {
            returning = true
            val next = inspect(windowId, lines, at, sensitive, false, canBackward, requireParameters = requireParameters)
            return if (next.move == Move.BACKWARD) next.copy(cause = Cause.QUOTES_CAPTURED) else next
        }
        if (canForward) {
            if (forward >= 8) return stop("Scrollgrenze erreicht. Keine vollständige Seitenprüfung; kein Entwurf übernommen.", Cause.SCROLL_LIMIT)
            forward++
            return Step(Move.FORWARD, ProductScreenEvidence.Result(message = "Bob liest die Produktseite abschnittsweise. Bitte währenddessen nicht bedienen."))
        }
        if (forward == 0 && candidate == null) {
            reset()
            return Step(Move.NONE, observed.copy(message = "Produktkennung erkannt, aber noch keine eindeutige Scrollfläche oder verwertbaren Kurse. Bob wartet auf den Seitenaufbau."), Cause.WAIT_SCROLL)
        }
        returning = true
        return inspect(windowId, lines, at, sensitive, false, canBackward, requireParameters = requireParameters)
    }
}
