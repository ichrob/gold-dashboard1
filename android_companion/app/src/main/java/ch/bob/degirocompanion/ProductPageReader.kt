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
    private var seekingSymbol: String? = null
    private var verifiedProbeSymbol: String? = null
    private var collectingHeader = false
    private var seekingParameters: Map<String, String> = emptyMap()
    private var isin: String? = null
    private var window: Int? = null
    private var readBackward = false
    private var returning = false
    private var forward = 0
    private var backward = 0
    private var returnSurfaceWaits = 0
    private var anchorParameters: Map<String, String> = emptyMap()
    private var candidate: ProductScreenEvidence.Result? = null
    val anchored get() = isin != null
    fun sameWindow(windowId: Int): Boolean = (anchored && window == windowId) || (seekingSymbol != null && seekWindow == windowId)
    fun reset() { verifiedProbeSymbol = null; collectingHeader = false; readBackward = false; seekingSymbol = null; seekingParameters = emptyMap(); rejectedForward = 0; rejectedBackward = 0; layoutWaits = 0; seekSteps = 0; seekWindow = null; isin = null; window = null; returning = false; forward = 0; backward = 0; returnSurfaceWaits = 0; candidate = null; anchorParameters = emptyMap() }
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
                canForward: Boolean, canBackward: Boolean, scrollAmbiguous: Boolean = false, requireParameters: Boolean = false, identityHint: String? = null,
                allowSymbolProbe: Boolean = false, requestedTermsOnly: Set<String> = emptySet(),
                seekLeverage: Boolean = false, expectedIsin: String? = null): Step {
        fun scopedParameters(values: List<QuoteLayout.Line>) = QuoteLayout.extract(values)
            .filterKeys { it in setOf("Hebel", "KO-Schwelle", "Basispreis", "Bv") }
        val direct = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines, at, sensitive,
            allowTermsOnly = requestedTermsOnly.isNotEmpty())
        // Launch/login transitions must not consume an unanchored request. Read nothing
        // from them; only wait within the existing 60-second request budget.
        if (!anchored && seekingSymbol == null && direct.reason in setOf(ProductScreenEvidence.Reason.PROTECTED, ProductScreenEvidence.Reason.LOGIN_OR_ORDER))
            return Step(Move.NONE, direct.copy(message = "Geschützte oder Login-Ansicht übersprungen. Bob wartet auf die Produktseite; nichts übernommen."), Cause.WAIT_PROTECTED)
        if (direct.reason in setOf(ProductScreenEvidence.Reason.PROTECTED, ProductScreenEvidence.Reason.LOGIN_OR_ORDER,
                ProductScreenEvidence.Reason.TOO_LARGE, ProductScreenEvidence.Reason.ISIN_INVALID,
                ProductScreenEvidence.Reason.ISIN_AMBIGUOUS)) return stop(direct.message, Cause.UNSAFE_VIEW, direct.reason)
        val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(lines.joinToString("\n") { it.text.uppercase() }).map { it.value }.distinct().toList()
        if (seekingSymbol != null && (windowId != seekWindow ||
                lines.mapNotNull { ProductSymbolMemory.probeHeaderSymbol(it.text) }.any { it != seekingSymbol }))
            return stop("Produkt oder Fenster bei der ISIN-Suche gewechselt.", Cause.IDENTITY_CHANGED)
        // Identity changes must be rejected even while the scroll tree is transient.
        if (anchored && (identityHint != null && identityHint != isin || windowId != window || (ids.isNotEmpty() && ids.singleOrNull() != isin)))
            return stop("Produkt oder Fenster gewechselt. Seitenprüfung abgebrochen.", Cause.IDENTITY_CHANGED)
        // An explicit same-screen Symbol | ISIN pair is an independent identity
        // check. It must match the current requested product; a search target
        // or cached broker symbol alone never authorizes publishing a draft.
        val footerPair = if (allowSymbolProbe && ids.size == 1)
            ProductSymbolMemory.observe(lines, sensitive)?.takeIf {
                it.isin == ids.single() &&
                    (expectedIsin == null || expectedIsin == it.isin) &&
                    (identityHint == null || identityHint == it.isin) &&
                    (seekingSymbol == null || seekingSymbol == it.symbol) &&
                    (verifiedProbeSymbol == null || verifiedProbeSymbol == it.symbol) &&
                    lines.mapNotNull { line -> ProductSymbolMemory.probeHeaderSymbol(line.text) }
                        .all { visible -> visible == it.symbol }
            } else null
        val verifiedPairedQuote = footerPair != null && direct.draft.isNotBlank() &&
            (expectedIsin != null || (seekingSymbol != null && seekingParameters.isNotEmpty())) &&
            listOf("Geld", "Brief", "Zuletzt").any {
                direct.draft.contains("$it (Anzeige ungeprüft): ")
            }
        // A return has already been requested and the original exact ISIN
        // is visible again. No scroll target is needed to finish this read.
        // An ambiguous scroll container must not discard the verified round
        // trip; protected/changed-product checks above remain mandatory.
        val originalIdentityRechecked = returning && candidate != null && ids.singleOrNull() == isin
        if (scrollAmbiguous && !originalIdentityRechecked && !verifiedPairedQuote) {
            if (anchored && ++layoutWaits > 5)
                return stop("Scrollbereich nach fünf Nachprüfungen weiterhin uneindeutig. Kein Entwurf übernommen.", Cause.SCROLL_LAYOUT_CHANGED)
            return Step(Move.NONE, direct.copy(draft = "", message = "Seitenaufbau noch nicht eindeutig. Bob wartet innerhalb des 60-Sekunden-Limits auf den Produktbereich."), Cause.WAIT_SCROLL_LAYOUT)
        }
        layoutWaits = 0
        // On the actual DEGIRO Mini-Future, the original ISIN is visibly paired
        // with its numeric symbol right beside the one-sided CHF quote.
        // That CURRENT screen needs no backward/forward scroll to establish
        // identity. A checked quote is always an unverified historical reading.
        if (verifiedPairedQuote) {
            val pair = footerPair!!
            val observedTerms = scopedParameters(lines)
            val earlierSymbol = seekingSymbol ?: verifiedProbeSymbol
            val earlierTerms = if (seekingSymbol != null) seekingParameters else anchorParameters
            val sameHeader = earlierSymbol == pair.symbol &&
                observedTerms.all { (key,value) -> earlierTerms[key]?.let { it == value } ?: true }
            val terms = if (sameHeader) earlierTerms + observedTerms else observedTerms
            val extras = terms.filterKeys { !direct.draft.contains("$it (Anzeige ungeprüft): ") }
                .map { (key,value) -> "$key (Anzeige ungeprüft): $value" }.joinToString("\n")
            val saved = if (extras.isEmpty()) direct else direct.copy(draft = direct.draft + "\n" + extras)
            reset()
            return Step(Move.FINISHED, saved.copy(message =
                "Sichtbares Symbol und ISIN auf der Kursseite bestätigt. " +
                "Historische App-Beobachtung, kein Handelsnachweis."))
        }
        if (!anchored) {
            // Discovery never substitutes the requested ISIN or stores prices from an unidentified page.
            if (allowSymbolProbe && ids.isEmpty()) {
                val symbol = ProductSymbolMemory.detailSymbol(lines.map { it.text })
                if (seekingSymbol == null && symbol != null) {
                    seekingSymbol = symbol; seekWindow = windowId
                    seekingParameters = QuoteLayout.productParameters(lines)
                }
                if (seekingSymbol != null) {
                    // A verified product-symbol header with explicit product
                    // parameters may need two additional bounded sections to
                    // reach its real ISIN in DEGIRO's long detail layout.
                    // A symbol alone still gets only four steps. Neither case
                    // substitutes the requested ISIN or publishes a draft.
                    val limit = if (seekingParameters.isNotEmpty()) 6 else 4
                    if (!canForward || seekSteps >= limit || MorningReadPolicy.detailFooter(lines.map { it.text }))
                        return stop("ISIN nach begrenzter Produktsuche nicht gefunden. Nichts übernommen.", Cause.SEEK_LIMIT)
                    seekSteps++
                    return Step(Move.FORWARD, ProductScreenEvidence.Result(message = "Bob sucht die echte ISIN in den Produktdetails; noch keine Werte übernommen."), Cause.SEEK_HEADER)
                }
            }
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
            anchorParameters = scopedParameters(lines)
            // Carry header parameters only after an explicit symbol/ISIN row confirms the pairing.
            if (seekingSymbol != null) {
                if (footerPair != null) {
                    // A labelled one-sided historical quote and exact visible
                    // Symbol|ISIN can complete this single-window transaction
                    // without reversing the scrolling direction twice.
                    // Never fabricate the missing Brief or a leverage.
                    val terms = scopedParameters(lines)
                    if (terms.any { (key, value) ->
                        seekingParameters[key]?.let { it != value } ?: false
                    }) return stop("Widersprüchliche Produktparameter im identischen Symbol.", Cause.IDENTITY_CHANGED)
                    anchorParameters = seekingParameters + terms
                    if (verifiedPairedQuote) {
                        val extra = anchorParameters.filterKeys {
                            !direct.draft.contains("$it (Anzeige ungeprüft): ")
                        }.map { (key, value) -> "$key (Anzeige ungeprüft): $value" }.joinToString("\n")
                        val answer = if (extra.isEmpty()) direct
                            else direct.copy(draft = direct.draft + "\n" + extra)
                        reset()
                        return Step(Move.FINISHED, answer.copy(
                            message = "Originalsymbol und ISIN auf einer sichtbaren Kursseite bestätigt. Historische, gegebenenfalls einseitige App-Werte bleiben ungeprüft."))
                    }
                }
                verifiedProbeSymbol = seekingSymbol
                readBackward = true
                seekingSymbol = null; seekingParameters = emptyMap()
            }
        }
        if (windowId != window || (ids.isNotEmpty() && ids.singleOrNull() != isin)) return stop("Produkt oder Fenster gewechselt. Seitenprüfung abgebrochen.", Cause.IDENTITY_CHANGED)
        // A header may appear across several scroll windows. Save additional
        // parameter evidence only when the *real* ISIN is visibly present in
        // this same window. Do not infer ownership from a search target or
        // merge contradictory readings into one apparent complete observation.
        if (ids.singleOrNull() == isin) {
            val observedParameters = scopedParameters(lines)
            if (observedParameters.all { (key, value) ->
                    anchorParameters[key]?.let { it == value } ?: true
                }) anchorParameters = anchorParameters + observedParameters
        }
        // Informational footers contain no additional quote evidence. Preserve the
        // candidate and return to the original identity within this transaction.
        if (!readBackward && MorningReadPolicy.detailFooter(lines.map { it.text })) returning = true
        // Numeric headers have no ISIN. Revisit that exact header after finding
        // the real identity, then return to the real ISIN before exporting anything.
        // This is transaction-local evidence, never a durable symbol mapping.
        if (collectingHeader) {
            val symbol = ProductSymbolMemory.detailSymbol(lines.map { it.text })
            val visibleSymbols = lines.mapNotNull { ProductSymbolMemory.probeHeaderSymbol(it.text) }.distinct()
            if (visibleSymbols.any { it != verifiedProbeSymbol })
                return stop("Produktkennung bei der Kopfzeilenprüfung gewechselt.", Cause.IDENTITY_CHANGED)
            if (symbol == verifiedProbeSymbol || !canBackward || backward >= 8) {
                if (symbol != null && symbol == verifiedProbeSymbol)
                    anchorParameters = anchorParameters + scopedParameters(lines)
                collectingHeader = false
                returning = true
            } else {
                backward++
                return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "Bob liest die Produktparameter im ursprünglichen Kopfbereich."))
            }
        }
        if (returning) {
            if (ids.singleOrNull() == isin) {
                // Read compact parameters only after the original ISIN has been
                // rechecked on return. Do not reuse a different page's title.
                val currentParameters = scopedParameters(lines)
                // The first and the returned header can contain complementary
                // fields. Keep the original evidence if a value conflicts.
                val parameters = if (currentParameters.all { (key, value) ->
                        anchorParameters[key]?.let { it == value } ?: true
                    }) anchorParameters + currentParameters else anchorParameters
                if (!readBackward && requireParameters && parameters.isEmpty() && canBackward && backward < 4) {
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
            if (readBackward) {
                if (!canForward && forward < 8 && returnSurfaceWaits++ < 3)
                    return Step(Move.NONE, ProductScreenEvidence.Result(
                        message="Rückkehrfläche wird erneut geprüft; kein Wert übernommen."), Cause.WAIT_SCROLL_LAYOUT)
                if (!canForward || forward >= 8) return stop("Rückprüfung der ISIN in den Details nicht möglich.", Cause.RETURN_FAILED)
                returnSurfaceWaits = 0
                forward++
                return Step(Move.FORWARD, ProductScreenEvidence.Result(message = "Bob prüft die echte ISIN erneut in den Produktdetails."))
            }
            if (!canBackward && backward < 8 && candidate != null && returnSurfaceWaits++ < 3)
                return Step(Move.NONE, ProductScreenEvidence.Result(
                    message="Rückwärts-Scrollfläche wird erneut geprüft; kein Wert übernommen."), Cause.WAIT_SCROLL_LAYOUT)
            if (!canBackward || backward >= 8) return stop("Rückprüfung der ISIN nicht möglich. Kein Entwurf übernommen.", Cause.RETURN_FAILED)
            returnSurfaceWaits = 0
            backward++
            return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "Bob kehrt zur Produktkennung zurück und prüft die Zuordnung."))
        }
        // Identity is carried only within this uninterrupted, same-window scroll transaction.
        val sample = if (ids.isEmpty()) lines + QuoteLayout.Line("ISIN: $isin", -100, -100, -1, -1) else lines
        val observed = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, sample, at, sensitive,
            allowTermsOnly = requestedTermsOnly.isNotEmpty())
        if (observed.reason == ProductScreenEvidence.Reason.QUOTES_INVALID) return stop(observed.message, Cause.INVALID_QUOTES, observed.reason)
        if (ProductDraftQuality.preferScreen(candidate?.draft.orEmpty(), observed.draft)) candidate = observed
        // A single, authentic identity header with ALL requested term fields
        // can complete a bounded read without an unavailable bid/ask pair.
        // No inferred source time or trade execution accompanies the draft.
        if (requestedTermsOnly.isNotEmpty() && ids.singleOrNull() == isin &&
            observed.draft.isNotBlank() && requestedTermsOnly.all {
                observed.draft.contains("$it (Anzeige ungeprüft): ")
            }) {
            returning = true
            return inspect(windowId, lines, at, sensitive, canForward, canBackward,
                requireParameters = requireParameters, requestedTermsOnly = requestedTermsOnly,
                seekLeverage = seekLeverage)
        }
        // The broker's overview often shows a full dated bid/ask pair but no
        // leverage. When that field was explicitly requested, read up to three
        // additional product-scoped sections and return to the real ISIN.
        // Never combine bid/ask from different screens or guess a leverage.
        val savedQuote = candidate?.draft.orEmpty().let {
            it.contains("Geld (Anzeige ungeprüft): ") && it.contains("Brief (Anzeige ungeprüft): ")
        }
        if (seekLeverage && savedQuote && !readBackward) {
            if (anchorParameters.containsKey("Hebel")) {
                returning = true
                return inspect(windowId, lines, at, sensitive, canForward, canBackward,
                    requireParameters = requireParameters, requestedTermsOnly = requestedTermsOnly,
                    seekLeverage = seekLeverage)
            }
            if (canForward && forward < 3) {
                forward++
                return Step(Move.FORWARD, ProductScreenEvidence.Result(
                    message = "Bob sucht den ausdrücklich beschrifteten Hebel in den nächsten Produktabschnitten."))
            }
            returning = true
            return inspect(windowId, lines, at, sensitive, canForward, canBackward,
                requireParameters = requireParameters, requestedTermsOnly = requestedTermsOnly,
                seekLeverage = seekLeverage)
        }
        // A complete labelled quote pair is the useful end of this read. Avoid
        // scrolling through unrelated footer sections or probing the page bottom.
        // Publication still requires returning to the original visible ISIN.
        if (observed.draft.contains("Geld (") && observed.draft.contains("Brief (")) {
            if (readBackward && requireParameters && verifiedProbeSymbol != null &&
                !anchorParameters.keys.containsAll(listOf("Hebel", "KO-Schwelle", "Basispreis", "Bv"))) {
                collectingHeader = true
            } else returning = true
            val next = inspect(windowId, lines, at, sensitive, canForward, canBackward, requireParameters = requireParameters, requestedTermsOnly = requestedTermsOnly,
                seekLeverage = seekLeverage)
            return if (next.move == Move.BACKWARD) next.copy(cause = Cause.QUOTES_CAPTURED) else next
        }
        if (readBackward) {
            if (canBackward && backward < 8) {
                backward++
                return Step(Move.BACKWARD, ProductScreenEvidence.Result(message = "ISIN erkannt. Bob liest die darüberliegenden Kursdaten.", reason = observed.reason))
            }
            returning = true
            return inspect(windowId, lines, at, sensitive, canForward, canBackward, requireParameters = requireParameters, requestedTermsOnly = requestedTermsOnly,
                seekLeverage = seekLeverage)
        }
        if (canForward) {
            if (forward >= 8) return stop("Scrollgrenze erreicht. Keine vollständige Seitenprüfung; kein Entwurf übernommen.", Cause.SCROLL_LIMIT)
            forward++
            return Step(Move.FORWARD, ProductScreenEvidence.Result(message = "Bob liest die Produktseite abschnittsweise. Bitte währenddessen nicht bedienen.", reason = observed.reason))
        }
        if (forward == 0 && candidate == null) {
            reset()
            return Step(Move.NONE, observed.copy(message = "Produktkennung erkannt, aber noch keine eindeutige Scrollfläche oder verwertbaren Kurse. Bob wartet auf den Seitenaufbau."), Cause.WAIT_SCROLL)
        }
        returning = true
        return inspect(windowId, lines, at, sensitive, canForward, canBackward, requireParameters = requireParameters, requestedTermsOnly = requestedTermsOnly,
                seekLeverage = seekLeverage)
    }
}
